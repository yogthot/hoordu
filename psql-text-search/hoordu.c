#include "postgres.h"
#include "commands/defrem.h"
#include "tsearch/ts_public.h"
#include "tsearch/ts_locale.h"

typedef struct
{
    char   *begin;
    char   *end;
    char   *p;
} TagParserStatus;

/* Output token categories */

#define TAG_TOKEN      1
#define FULLTAG_TOKEN  2

#define LAST_TOKEN_NUM 2

static const char *const tok_alias[] = {
    "",
    "tag",
    "fulltag"
};

static const char *const lex_descr[] = {
    "",
    "A tag",
    "A tag with category"
};

PG_MODULE_MAGIC;

PG_FUNCTION_INFO_V1(hoordu_tagparser_start);
PG_FUNCTION_INFO_V1(hoordu_tagparser_nexttoken);
PG_FUNCTION_INFO_V1(hoordu_tagparser_end);
PG_FUNCTION_INFO_V1(hoordu_tagparser_lextype);
PG_FUNCTION_INFO_V1(hoordu_tagdict_init);
PG_FUNCTION_INFO_V1(hoordu_tagdict_lexize);

Datum
hoordu_tagparser_start(PG_FUNCTION_ARGS)
{
    TagParserStatus *status = (TagParserStatus *) palloc0(sizeof(TagParserStatus));
    
    status->begin = (char *) PG_GETARG_POINTER(0);
    status->end = status->begin + PG_GETARG_INT32(1);
    status->p = status->begin;
    
    PG_RETURN_POINTER(status);
}

Datum
hoordu_tagparser_nexttoken(PG_FUNCTION_ARGS)
{
    TagParserStatus *status = (TagParserStatus *) PG_GETARG_POINTER(0);
    char **t = (char **) PG_GETARG_POINTER(1);
    int *tlen = (int *) PG_GETARG_POINTER(2);
    bool found = false, end = false, has_category = false;
    
    while (status->p < status->end && !end)
    {
        int p_len = pg_mblen(status->p);
        
        if (p_len == 1)
        {
            switch (*status->p){
            case ' ':
                // end of the token
                if (found)
                    end = true;
                break;
            
            case ':':
                // this token begins with a category name (need to force tags to not contain :)
                has_category = true;
                break;
            
            default:
                // valid token character
                if (!found)
                {
                    *t = status->p;
                    found = true;
                }
                break;
            }
        }
        else
        {
            if (!found)
            {
                *t = status->p;
                found = true;
            }
        }
        status->p += p_len;
    }
    
    if (found)
    {
        *tlen = status->p - *t;
        if (!has_category)
            PG_RETURN_INT32(TAG_TOKEN);
        else
            PG_RETURN_INT32(FULLTAG_TOKEN);
    }
    else
    {
        PG_RETURN_INT32(0);
    }
}

Datum
hoordu_tagparser_end(PG_FUNCTION_ARGS)
{
    TagParserStatus *status = (TagParserStatus *) PG_GETARG_POINTER(0);
    
    pfree(status);
    PG_RETURN_VOID();
}


Datum
hoordu_tagparser_lextype(PG_FUNCTION_ARGS)
{
    LexDescr *descr = (LexDescr *) palloc(sizeof(LexDescr) * (LAST_TOKEN_NUM + 1));
    int i;
    
    for (i = 1; i <= LAST_TOKEN_NUM; i++)
    {
        descr[i - 1].lexid = i;
        descr[i - 1].alias = pstrdup(tok_alias[i]);
        descr[i - 1].descr = pstrdup(lex_descr[i]);
    }
    
    descr[LAST_TOKEN_NUM].lexid = 0;
    
    PG_RETURN_POINTER(descr);
}

typedef struct
{
    int split_tags;
} TagDict;

Datum
hoordu_tagdict_init(PG_FUNCTION_ARGS)
{
    List *dictoptions = (List *) PG_GETARG_POINTER(0);
    TagDict *d = (TagDict *) palloc0(sizeof(TagDict));
    bool split_tags_loaded = false;
    
    ListCell *l;
    foreach(l, dictoptions)
    {
        DefElem *defel = (DefElem *) lfirst(l);

        if (pg_strcasecmp("split_tags", defel->defname) == 0)
        {
            if (split_tags_loaded)
                ereport(ERROR,
                        (errcode(ERRCODE_INVALID_PARAMETER_VALUE),
                         errmsg("multiple split_tags parameters")));
            d->split_tags = atoi(defGetString(defel));
            split_tags_loaded = true;
        }
        else
        {
            ereport(ERROR,
                    (errcode(ERRCODE_INVALID_PARAMETER_VALUE),
                     errmsg("unrecognized dictionary parameter: \"%s\"",
                            defel->defname)));
        }
    }
    
    if (!split_tags_loaded)
        d->split_tags = 0;
    
    PG_RETURN_POINTER(d);
}

Datum
hoordu_tagdict_lexize(PG_FUNCTION_ARGS)
{
    TagDict *d = (TagDict *) PG_GETARG_POINTER(0);
    char *in = (char *) PG_GETARG_POINTER(1);
    int32 len = PG_GETARG_INT32(2);
    char *txt;
    int strlen;
    TSLexeme *res;
    int i;
    bool found_colon = false;
    
    res = palloc0(sizeof(TSLexeme) * 4);
    txt = lowerstr_with_len(in, len);
    strlen = pg_mbstrlen(txt);
    
    res[0].nvariant = 1;
    res[0].lexeme = txt;
    
    if (d->split_tags == 1)
    {
        for (i = 0; i < strlen; i++)
        {
            int p_len = pg_mblen(txt);
            
            if (p_len == 1 && *txt == ':')
            {
                found_colon = true;
            }
            
            txt += p_len;
            
            if (found_colon)
                break;
        }
        
        if (found_colon)
        {
            res[1].nvariant = 2;
            res[1].lexeme = pstrdup(txt);
        }
    }
    
    PG_RETURN_POINTER(res);
}
