-- complain if script is sourced in psql, rather than via CREATE EXTENSION
\echo Use "CREATE EXTENSION hoordu;" to load this file. \quit

CREATE OR REPLACE FUNCTION hoordu_tagparser_start(internal, integer)
	RETURNS internal
	AS 'MODULE_PATHNAME'
	LANGUAGE C STRICT IMMUTABLE;

CREATE OR REPLACE FUNCTION hoordu_tagparser_nexttoken(internal, internal, internal)
	RETURNS internal
	AS 'MODULE_PATHNAME'
	LANGUAGE C STRICT IMMUTABLE;

CREATE OR REPLACE FUNCTION hoordu_tagparser_end(internal)
	RETURNS void
	AS 'MODULE_PATHNAME'
	LANGUAGE C STRICT IMMUTABLE;

CREATE OR REPLACE FUNCTION hoordu_tagparser_lextype(internal)
	RETURNS internal
	AS 'MODULE_PATHNAME'
	LANGUAGE C STRICT IMMUTABLE;

CREATE TEXT SEARCH PARSER hoordu_tag_parser (
	START = hoordu_tagparser_start,
	GETTOKEN = hoordu_tagparser_nexttoken,
	END = hoordu_tagparser_end,
	LEXTYPES = hoordu_tagparser_lextype
);
COMMENT ON TEXT SEARCH PARSER hoordu_tag_parser IS 'hoordu tag parser';

CREATE OR REPLACE FUNCTION hoordu_tagdict_init(internal)
	RETURNS internal
	AS 'MODULE_PATHNAME'
	LANGUAGE C STRICT IMMUTABLE;

CREATE OR REPLACE FUNCTION hoordu_tagdict_lexize(internal, internal, internal, internal)
	RETURNS internal
	AS 'MODULE_PATHNAME'
	LANGUAGE C STRICT IMMUTABLE;

CREATE TEXT SEARCH TEMPLATE hoordu_tagtmpl (
	INIT = hoordu_tagdict_init,
	LEXIZE = hoordu_tagdict_lexize
);
COMMENT ON TEXT SEARCH TEMPLATE hoordu_tagtmpl IS 'hoordu tag dictionary template';

CREATE TEXT SEARCH DICTIONARY hoordu_tagdict_v (
	TEMPLATE = hoordu_tagtmpl,
    split_tags = 1
);
COMMENT ON TEXT SEARCH DICTIONARY hoordu_tagdict_v IS 'hoordu tag dictionary configured for vectors';

CREATE TEXT SEARCH CONFIGURATION hoordu_tags_v (
	PARSER = hoordu_tag_parser
);
ALTER TEXT SEARCH CONFIGURATION hoordu_tags_v ADD MAPPING FOR tag WITH hoordu_tagdict_v;
ALTER TEXT SEARCH CONFIGURATION hoordu_tags_v ADD MAPPING FOR fulltag WITH hoordu_tagdict_v;
COMMENT ON TEXT SEARCH CONFIGURATION hoordu_tags_v IS 'hoordu tag configuration for vectors';


CREATE TEXT SEARCH DICTIONARY hoordu_tagdict_q (
	TEMPLATE = hoordu_tagtmpl,
    split_tags = 0
);
COMMENT ON TEXT SEARCH DICTIONARY hoordu_tagdict_q IS 'tag dictionary';

CREATE TEXT SEARCH CONFIGURATION hoordu_tags_q (
	PARSER = hoordu_tag_parser
);
ALTER TEXT SEARCH CONFIGURATION hoordu_tags_q ADD MAPPING FOR tag WITH hoordu_tagdict_q;
ALTER TEXT SEARCH CONFIGURATION hoordu_tags_q ADD MAPPING FOR fulltag WITH hoordu_tagdict_q;
COMMENT ON TEXT SEARCH CONFIGURATION hoordu_tags_q IS 'hoordu tag configuration for queries';
