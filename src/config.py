from config_local import SURVEYMONKEY_API_TOKEN

UNPROCESSED_FOLDER_ID = "FOLDER_ID_UNPROCESSED"
PROCESSED_FOLDER_ID = "FOLDER_ID_PROCESSED"

# Google Sheets
SHEET_IDS = {
    "Subscription/Classical": "TODO",
    "Pops/Family": "TODO",
    "Opera": "TODO"
}

# SurveyMonkey survey templates (can also store survey IDs directly)
SURVEY_TEMPLATES = {
    "Classical": "Template A",
    "Pops": "Template B",
    "Family": "Template C"
}
# Optional default email subject/body
DEFAULT_SUBJECT = "Conductor Evaluation for {title}"
DEFAULT_BODY = "Hello! Please complete the survey for {title}."
