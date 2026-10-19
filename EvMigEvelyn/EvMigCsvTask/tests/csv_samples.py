"""Test inputs: the CSV files that Evelyn's CsvDataServiceTest and CsvTaskProcessorIT read, re-created.

Java keeps them as files under names-screening-jnw/src/test/resources/csv/ (the folder is called `csv/` below). Each constant
says which file it stands for. The format files only name columns, so they are copied as they are. In the data files every
person and company is replaced by a placeholder (Alice Wonderland, John Doe, Gill Bates and spellings of them); the
columns, the blank cells, the odd spaces and the row order, which are what the tests are about, are kept.
Strings, not files, so that a BOM, a blank line or a missing final newline is written out where it matters.
"""

# csv/format-file/nss_correct_format.csv
NSS_CORRECT_FORMAT = 'nss_column,client_column\n"input_id",id\n"input_record_type","record_type"\n"input_full_name", "NAME "\n"input_alias_name",\n"input_date_1",date,\n"input_date_type_1",\n"input_address_1_street",\n"input_address_1_city",\n"input_address_1_state",\n"input_address_1_country",address\n"input_address_1_postal_code",\n"input_address_1_type",\n"input_gender",\n"hit_id",\n"hit_record_type",\n"hit_matched_name",        "  MATCHED_name "\n"hit_primary_name",other_name\n"hit_matched_name_score",\n"hit_gender",\n"hit_address_1_street",\n"hit_address_1_city",\n"hit_address_1_state",\n"hit_address_1_country",matched_address\n"hit_address_1_postal_code",\n"hit_address_1_type",\n"hit_date_1", matched_date,\n"hit_date_type_1",\n'

# csv/format-file/nss_incorrect_format.csv
NSS_INCORRECT_FORMAT = 'nss_column,client_column\n"input_id",\n"input_record_type","record_type"\n"input_full_name",\n"input_alias_name",\n"input_date_1",date,\n"input_date_type_1",\n"input_address_1_street",\n"input_address_1_city",\n"input_address_1_state",\n"input_address_1_country",address\n"input_address_1_postal_code",\n"input_address_1_type",\n"input_gender",\n"hit_id",\n"hit_record_type",\n"hit_matched_name",\n"hit_primary_name",other_name\n"hit_matched_name_score",\n"hit_gender",\n"hit_address_1_street",\n"hit_address_1_city",\n"hit_address_1_state",\n"hit_address_1_country",matched_address\n"hit_address_1_postal_code",\n"hit_address_1_type",\n"hit_date_1", matched_date,\n"hit_date_type_1",\n'

# csv/format-file/nss_full_format.csv
NSS_FULL_FORMAT = 'nss_column,client_column\ninput_id,input_id\ninput_category,input_category\ninput_record_type,input_record_type\ninput_gender,input_gender\ninput_full_name,input_full_name\ninput_first_name,input_first_name\ninput_middle_name,input_middle_name\ninput_last_name,input_last_name\ninput_alias_name,input_alias_name\ninput_alias2_name,input_alias2_name\ninput_alias3_name,input_alias3_name\ninput_date_1,input_date_1\ninput_date_type_1,input_date_type_1\ninput_address_1_street,input_address_1_street\ninput_address_1_city,input_address_1_city\ninput_address_1_state,input_address_1_state\ninput_address_1_country,input_address_1_country\ninput_address_1_full,input_address_1_full\ninput_address_1_type,input_address_1_type\ninput_id_rn_extdata, input_id_rn_extdata\ninput_ID_identifier, input_ID_identifier\nhit_id,hit_id\nhit_record_type,hit_record_type\nhit_matched_name,hit_matched_name\nhit_primary_name,hit_primary_name\nhit_alias_name,hit_alias_name\nhit_alias2_name,hit_alias2_name\nhit_alias3_name,hit_alias3_name\nhit_gender,hit_gender\nhit_address_1_street,hit_address_1_street\nhit_address_1_city,hit_address_1_city\nhit_address_1_state,hit_address_1_state\nhit_address_1_country,hit_address_1_country\nhit_address_1_postal_code,hit_address_1_postal_code\nhit_address_1_type,hit_address_1_type\nhit_date_1,hit_date_1\nhit_date_type_1,hit_date_type_1\nalert_gold_resolution, input_gold_value\nhit_gold_resolution, hit_gold_value\nhit_id_rn_extdata,hit_id_rn_extdata\nhit_id_lei_extdata,hit_id_lei_extdata\nhit_id_crn_extdata,hit_id_crn_extdata\nhit_category,hit_category\nhit_passport_identifier, hit_passport_identifier'

# csv/nss_input_format.csv
NSS_INPUT_FORMAT = 'nss_column,client_column\n"input_id",id,\n"input_record_type","record_type"\n"input_full_name", "NAME "\n"input_alias_name",\n"input_date_1",date,\n"input_date_type_1",\n"input_address_1_street",\n"input_address_1_city",\n"input_address_1_state",\n"input_address_1_country",address\n"input_address_1_postal_code",\n"input_address_1_type",\n"input_gender",\n"hit_id",\n"hit_record_type",\n"hit_matched_name",        "  MATCHED_name "\n"hit_primary_name",other_name\n"hit_matched_name_score",\n"hit_gender",\n"hit_address_1_street",\n"hit_address_1_city",\n"hit_address_1_state",\n"hit_address_1_country",matched_address\n"hit_address_1_postal_code",\n"hit_address_1_type",\n"hit_date_1", matched_date,\n"hit_date_type_1",\n"hit_matched_country",\n"hit_matched_country_score",\n"hit_IDs_match",\n"input_hits_size",\n"hit_gold_resolution", "hit_gold_resolution"'

# csv/input-data-1-input-id-3-hits.csv (every name replaced by a placeholder)
INPUT_DATA_1_INPUT_ID_3_HITS = 'input_id,input_id_rn_extdata,input_category,input_record_type,input_gender,input_gold_value,input_full_name,input_first_name,input_middle_name,input_last_name,input_alias_name,input_alias2_name,input_alias3_name,input_date_1,input_date_type_1,input_address_1_street,input_address_1_city,input_address_1_state,input_address_1_country,input_address_1_full,input_address_1_type,input_ID_identifier,hit_id,hit_record_type,hit_matched_name,hit_primary_name,hit_alias_name,hit_alias2_name,hit_alias3_name,hit_gender,hit_address_1_street,hit_address_1_city,hit_address_1_state,hit_address_1_country,hit_address_1_full,hit_address_1_type,hit_date_1,hit_date_type_1,hit_id_rn_extdata,hit_id_lei_extdata,hit_id_crn_extdata,hit_category,hit_gold_value,hit_passport_identifier\n1,11,high,ORGANIZATION,Male,1,Gill Bates Holdings,,,,GBH,GBH2,,03-2001,,street 1,city 1,CA,USA,full address 1,type 1,1211,1,ORGANIZATION,Gill Bates Holdings,name1,bank1,bank2,,Male,street 1,city 1,CA,USA,full address 1,type 1,2023,type 1,,0011,1212,category, 1,2222\n1,11,high,ORGANIZATION,,,Gill Bates Holdings AAG,,,,Gill baaanka,other bank alias,,21.01.2001,,street 2,city 2,,USA,full address 2,type 2,1211,2,ORGANIZATION,Gill Bates Holdings AAG,name2,bank1_only,,,,street 2,city 2,,USA,full address 2,type 2,01.01.2023,type 2,,0011,1212,category, 1,2222\n2,11,low,INDIVIDUAL,Male,,John,Doe,John,Markus,,,,1/21/2001,DOB,street 3,city 3,AL,USA,full address 3,type 3,,3,INDIVIDUAL,John,name3,,,,Male,street 3,city 3,AL,USA,full address 3,type 3,02-2023,type 3,,0011,1212,category, 1,2222\n3,11,medium,SECURITIES,,,123 SECURITIES,,,,ABC,,,,,,city 4,,USA,full address 4,type 4,,4,SECURITIES,123 SECURITIES,name4,,nothing above,,,,city 4,,USA,full address 4,type 4,09/2023,type 4,,0011,1212,category, 1,2222'

# csv/input-data-1-input-id-4-hits-location.csv
INPUT_DATA_1_INPUT_ID_4_HITS_LOCATION = 'input_id,input_id_rn_extdata,input_category,input_record_type,input_gender,input_gold_value,input_full_name,input_first_name,input_middle_name,input_last_name,input_alias_name,input_alias2_name,input_alias3_name,input_date_1,input_date_type_1,input_address_1_street,input_address_1_city,input_address_1_state,input_address_1_country,input_address_1_full,input_address_1_type,input_ID_identifier,hit_id,hit_record_type,hit_matched_name,hit_primary_name,hit_alias_name,hit_alias2_name,hit_alias3_name,hit_gender,hit_address_1_city,hit_address_1_state,hit_address_1_country,hit_address_1_full,hit_address_1_type,hit_date_1,hit_date_type_1,hit_id_rn_extdata,hit_id_lei_extdata,hit_id_crn_extdata,hit_category,hit_gold_value,hit_passport_identifier\n1,11,high,ORGANIZATION,Male,1,Gill Bates Holdings,,,,GBH,GBH2,,03-2001,,street 1,city 1,CA,USA,full address 1,type 1,1211,1,ORGANIZATION,Gill Bates Holdings,name1,bank1,bank2,,Male,city 1,CA,USA,full address 1,type 1,2023,type 1,,0011,1212,category, 1,2222\n1,11,high,ORGANIZATION,,,Gill Bates Holdings AAG,,,,Gill baaanka,other bank alias,,21.01.2001,,street 2,city 2,,USA,full address 2,type 2,1211,2,ORGANIZATION,Gill Bates Holdings AAG,name2,bank1_only,,,,city 2,,USA,full address 2,type 2,01.01.2023,type 2,,0011,1212,category, 1,2222\n2,11,low,INDIVIDUAL,Male,,John,Doe,John,Markus,,,,1/21/2001,DOB,street 3,city 3,AL,USA,full address 3,type 3,,3,INDIVIDUAL,John,name3,,,,Male,city 3,AL,USA,full address 3,type 3,02-2023,type 3,,0011,1212,category, 1,2222\n3,11,medium,SECURITIES,,,123 SECURITIES,,,,ABC,,,,,street 4,city 4,,USA,full address 4,type 4,,4,SECURITIES,123 SECURITIES,name4,,nothing above,,,city 4,,USA,full address 4,type 4,09/2023,type 4,,0011,1212,category, 1,2222\n4,11,medium,INDIVIDUAL,,,location,,,,address,,,,,street 5,city 5,,USA,full address 5,type 5,,5,LOCATION,address,location,,,,,city 5,,USA,full address 5,type 5,09/2023,type 4,,0011,1212,category, 1,2222'

# csv/input_data_invalid_date_and_record_type.csv
INPUT_DATA_INVALID_DATE_AND_RECORD_TYPE = 'input_id,input_category,input_record_type,input_gender,input_full_name,input_first_name,input_middle_name,input_last_name,input_alias_name,input_date_1,input_date_type_1,input_address_1_street,input_address_1_city,input_address_1_state,input_address_1_country,input_address_1_full,input_address_1_type,hit_id,hit_record_type,hit_matched_name,hit_primary_name,hit_gender,hit_address_1_city,hit_address_1_state,hit_address_1_country,hit_address_1_full,hit_address_1_type,hit_date_1,hit_date_type_1\n1,high,ORGANIZATION,,Gill Bates Holdings,,,,GBH,03-2001,,street 1,city 1,CA,USA,full address 1,type 1,1,ORGANIZATION,Gill Bates Holdings,name1,,city 1,CA,USA,full address 1,type 1,2023,type 1\n1,high,ORGANIZATION,,Gill Bates Holdings AAG,,,,Gill baaanka,21.01.2001,,street 2,city 2,,USA,full address 2,type 2,2,ORGANIZATION,Gill Bates Holdings AAG,name2,,city 2,,USA,full address 2,type 2,01.01.2023,type 2\n2,low,INDIVIDUAL,Male,John,Doe,John,Markus,,31/21/2001,DOB,street 3,city 3,AL,USA,full address 3,type 3,3,INDIVIDUAL,John,name3,Male,city 3,AL,USA,full address 3,type 3,02-2023,type 3\n3,medium,SECURITIES,,123 SECURITIES,,,,ABC,,,street 4,city 4,,USA,full address 4,type 4,4,SECURITIES,123 SECURITIES,name4,,city 4,,USA,full address 4,type 4,2023,type 4\n4,medium,INVALID,,123 SECURITIES,,,,ABC,,,street 4,city 4,,USA,full address 4,type 4,5,SECURITIES,123 SECURITIES,name4,,city 4,,USA,full address 4,type 4,2023,type 4\n5,medium,INVALID,,123 SECURITIES,,,,ABC,,,street 4,city 4,,USA,full address 4,type 4,6,INVALID,123 SECURITIES,name4,,city 4,,USA,full address 4,type 4,2023,type 4\n6,medium,SECURITIES,,123 SECURITIES,,,,ABC,,,street 4,city 4,,USA,full address 4,type 4,7,INVALID,123 SECURITIES,name4,,city 4,,USA,full address 4,type 4,2023,type 4\n7,medium,,,123 SECURITIES,,,,ABC,,,street 4,city 4,,USA,full address 4,type 4,8,INDIVIDUAL,123 SECURITIES,name4,,city 4,,USA,full address 4,type 4,2023,type 4\n8,medium,INDIVIDUAL,,123 SECURITIES,,,,ABC,,,street 4,city 4,,USA,full address 4,type 4,9,,123 SECURITIES,name4,,city 4,,USA,full address 4,type 4,2023,type 4\n9,medium,,,123,,,,ABC,,,street 4,city 4,,USA,full address 4,type 4,10,,123 SECURITIES,name4,,city 4,,USA,full address 4,type 4,2023,type 4'

# csv/input-data-1-no-name-hit.csv
INPUT_DATA_1_NO_NAME_HIT = 'input_id,input_id_rn_extdata,input_category,input_record_type,input_gender,input_gold_value,input_full_name,input_first_name,input_middle_name,input_last_name,input_alias_name,input_alias2_name,input_alias3_name,input_date_1,input_date_type_1,input_address_1_street,input_address_1_city,input_address_1_state,input_address_1_country,input_address_1_full,input_address_1_type,input_ID_identifier,hit_id,hit_record_type,hit_matched_name,hit_primary_name,hit_alias_name,hit_alias2_name,hit_alias3_name,hit_gender,hit_address_1_city,hit_address_1_state,hit_address_1_country,hit_address_1_full,hit_address_1_type,hit_date_1,hit_date_type_1,hit_id_rn_extdata,hit_id_lei_extdata,hit_id_crn_extdata,hit_category,hit_gold_value,hit_passport_identifier\n1,11,high,TEST,Male,1,Gill Bates Holdings,,,,GBH,GBH2,,03-2001,,street 1,city 1,CA,USA,full address 1,type 1,1211,1,ORGANIZATION,,,,,,Male,city 1,CA,USA,full address 1,type 1,2023,type 1,,0011,1212,category, 1,2222'

# csv/input-data-no-hit-id.csv
INPUT_DATA_NO_HIT_ID = 'id,name,matched_name, hit_gold_resolution\n1,Gill Bates Holdings,Gill Bates Holdings, 1'

# csv/all-records-failed.csv (no names in it at all, copied as it is)
ALL_RECORDS_FAILED = 'id,client_id,category,entity_type,gender,name,first,middle,last,date_1,date_type_1,date_2,date_type_2,address_1_type,address_1_country,address_1_state,address_1_city,address_1_full,aliases,identifiers,additional_data,gold_decision,hit_id,hit_category,hit_entity_type,hit_gender,hit_name,hit_first,hit_middle,hit_last,hit_date_1,hit_date_type_1,hit_date_2,hit_date_type_2,hit_address_1_type,hit_address_1_country,hit_address_1_state,hit_address_1_city,hit_address_1_full,hit_aliases,hit_identifiers,hit_additional_data,hit_gold_decision\n,111,null,TEST,TEST,,,,, 06/test/1991,1123,test/10/2140,null,null,null,null,null,null,,null,null,null,1,null,TEST,TEST,,,,, 06/10/test,null,06/10/null,null,null,null,null,null,null,,null,null,null\n,112,null,TEST,TEST,,,,, 06/test/1991,1123,test/10/2140,null,null,null,null,null,null,,null,null,null,2,null,TEST,TEST,,,,, 06/10/test,null,06/10/null,null,null,null,null,null,null,,null,null,null\n,113,null,TEST,TEST,,,,, 06/test/1991,1123,test/10/2140,null,null,null,null,null,null,,null,null,null,3,null,TEST,TEST,,,,, 06/10/test,null,06/10/null,null,null,null,null,null,null,,null,null,null\n,114,null,location,TEST,,,,, 06/test/1991,1123,test/10/2140,null,null,null,null,null,null,,null,null,null,4,null,TEST,TEST,,,,, 06/10/test,null,06/10/null,null,null,null,null,null,null,,null,null,null\n,115,null,Location,TEST,,,,, 06/test/1991,1123,test/10/2140,null,null,null,null,null,null,,null,null,null,5,null,TEST,TEST,,,,, 06/10/test,null,06/10/null,null,null,null,null,null,null,,null,null,null'

# csv/data_file_with_bom_encoding.csv (the BOM is the first character)
DATA_FILE_WITH_BOM_ENCODING = '\ufeffsystem_id,db_name,id_list,name,hit_type,list_matching_string\n1234,some_name,someId,lines, LTD,Name,CAC'

# csv/format-file/format_file_with_bom_encoding.csv
FORMAT_FILE_WITH_BOM_ENCODING = '\ufeffnss_column,client_column\ninput_id,system_id\ninput_full_name,db_name\nhit_id,id_list\nhit_matched_name,name'


def _file(*lines):
    """A file's text from its lines, with no newline at the end (as the Java resources have it)."""
    return "\n".join(lines)


# csv/empty.csv
EMPTY = ""

# csv/only_headers_file.csv
ONLY_HEADERS_FILE = _file("id,name,matched_name")

# csv/input-data-2-input-id-5-hits.csv: two alerts, the first with 3 hits and the second with 2, rows interleaved
INPUT_DATA_2_INPUT_ID_5_HITS = _file(
    "id,name,matched_name",
    "1,Alice Wonderland,Alice Wonderland",
    "2,John Doe,John Doe Jr",
    "1,Alice Wonderland-Smith,Alice Wonderland",
    "1,Alice Wonder,Alice Wonderland EE",
    "2,John Doe,John Doe",
)

# csv/combination-at-least-one-name-anywhere.csv: 10 rows, each with a name in a different one of the name columns
COMBINATION_AT_LEAST_ONE_NAME_ANYWHERE = _file(
    "id,name,input_alias,input_first,input_middle,input_last,hit_id,matched_name,hit_first,hit_middle,hit_last,hit_alias",
    "1,Gill, ,,,,11,Gill,,,,",
    "2,Gill, ,,,,12,,Gill,,,",
    "3,Gill, ,,,,13,,,Gill,,",
    "4,Gill, ,,,,14,,,,Gill,",
    "5,Gill, ,,,,15,,,,,Gill",
    "6,,Gill,,,,16,Gill,,,,",
    "7,,,Gill,,,17,Gill,,,,",
    "8,,,,Gill,,18,Gill,,,,",
    "9,,,,,Gill,19,Gill,,,,",
    "10,,,,,Gill,110,,,,,Gill",
)

# csv/input-data-no-input-and-hit-name.csv: line 1 has no input name, line 2 no hit name, line 3 repeats the id of
# line 2, line 4 has neither, line 5 is fine
INPUT_DATA_NO_INPUT_AND_HIT_NAME = _file(
    "id,name,matched_name,hit_id",
    "1,,Alice Wonderland,11",
    "2,Alice Wonderland,,12",
    "2,This line will be skipped,because it has same input id as previous line,13",
    "3,,,14",
    "4,Alice Wonderland,Alice Wonderland,15",
)

# csv/input-all-names-missing.csv: every row has no hit name
INPUT_ALL_NAMES_MISSING = _file(
    "id,name,matched_name",
    "1,Alice Wonderland,",
    "2,Alice Wonderland,",
    "3,Alice Wonderland,",
)

# csv/input-and-hit-data-combination-of-correct-and-wrong.csv: 9 alerts, 5 fine
INPUT_AND_HIT_DATA_COMBINATION_OF_CORRECT_AND_WRONG = _file(
    "id,name,matched_name",
    "1,John Doe,John Doe",
    "2,,John Doe",
    "3,,John Doe",
    "4,John Doe,John Doe",
    "5,John Doe,John Doe",
    "6,John Doe,John Doe",
    "7,John Doe,",
    "8,John Doe,",
    "9,John Doe,John Doe",
)

# csv/multiple-hits-assigned-to-same-input.csv: one alert, five hits, cells with a space in front
MULTIPLE_HITS_ASSIGNED_TO_SAME_INPUT = _file(
    "id,name,matched_name,hit_id",
    "1, Gill Bates, Gill Bates, 1",
    "1, Gill Bates, Gill Bates, 2",
    "1, Gill Bates, Gill Bates, 3",
    "1, Gill Bates, Gill Bates, 4",
    "1, Gill Bates, Gill Bates, 5",
)

# csv/all-records-correct.csv: one alert with one hit and every column filled
ALL_RECORDS_CORRECT = _file(
    "id,client_id,category,entity_type,gender,name,first,middle,last,date_1,date_type_1,date_2,date_type_2,address_1_type,address_1_country,address_1_state,address_1_city,address_1_full,aliases,identifiers,additional_data,gold_decision,hit_id,hit_category,hit_entity_type,hit_gender,hit_name,hit_first,hit_middle,hit_last,hit_date_1,hit_date_type_1,hit_date_2,hit_date_type_2,hit_address_1_type,hit_address_1_country,hit_address_1_state,hit_address_1_city,hit_address_1_full,hit_aliases,hit_identifiers,hit_additional_data,hit_gold_decision",
    "11,111,ORGAN,INDIVIDUAL,MALE,Alice Wonderland,Alice, Jane, Wonderland, 06/10/1991,DOB,06/10/2140,Death,Home,USA,CS,California,Grove Street,Ally Wonder,id = 1234 | PPSN = 54321000,id = 1234 | Passport = 999,1,12,ORGAN,INDIVIDUAL,MALE,Alice Wonderland,Alice, Jane, Wonderland, 06/10/1991,DOB,06/10/2140,Death,Home,USA,CS,California,Los Angeles,Ally Wonder,id = 1234 | PPSN = 54321000,id = 1234 | Passport = 999,1",
)

# csv/all-records-location-hit-type.csv: three alerts, each with one hit of type LOCATION
ALL_RECORDS_LOCATION_HIT_TYPE = _file(
    "id,entity_type,name,hit_id,hit_entity_type,hit_name",
    "1,SECURITIES,JOHN DOE,11,LOCATION,JOHN DOE",
    "2,SECURITIES,JOHN DOE,12,LOCATION,JOHN DOE",
    "3,SECURITIES,JOHN DOE,13,LOCATION,JOHN DOE",
)

# csv/mixed-records-security-and-location-hit-type.csv: 7 alerts; the first three have a LOCATION hit, the rest a SECURITIES hit
MIXED_RECORDS_SECURITY_AND_LOCATION_HIT_TYPE = _file(
    "id,entity_type,name,hit_id,hit_entity_type,hit_name",
    "1,SECURITIES,JOHN DOE,11,LOCATION,JOHN DOE",
    "2,SECURITIES,JOHN DOE,12,LOCATION,JOHN DOE",
    "3,SECURITIES,JOHN DOE,13,LOCATION,JOHN DOE",
    "4,SECURITIES,JOHN DOE,14,SECURITIES,JOHN DOE",
    "5,SECURITIES,JOHN DOE,15,SECURITIES,JOHN DOE",
    "6,SECURITIES,JOHN DOE,16,SECURITIES,JOHN DOE",
    "7,SECURITIES,JOHN DOE,17,SECURITIES,JOHN DOE",
)
