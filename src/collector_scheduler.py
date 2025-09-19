from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from google_sheets_api_client import GoogleSheetsApiClient
from surveymonkey_api_client import SurveyMonkeyApiClient
from config import SURVEY_TEMPLATES, UNPROCESSED_FOLDER_ID, PROCESSED_FOLDER_ID
from config_local import SURVEYMONKEY_API_TOKEN


class CollectorScheduler:
    def __init__(self):
        self.surveymonkey_client = SurveyMonkeyApiClient(SURVEYMONKEY_API_TOKEN)
        self.google_sheets_client = GoogleSheetsApiClient()

    def run(self):
        # Get all unprocessed sheets
        sheets = self.google_sheets_client.list_sheets_in_folder(UNPROCESSED_FOLDER_ID)
        for sheet_id, sheet_name in sheets:
            # Pull data from sheet and validate it
            event_title, conductor_name, event_date, recipient_emails_on_sheet = self.google_sheets_client.read_roster_sheet(sheet_id)
            if not self.is_google_sheet_valid(event_title, conductor_name, event_date, recipient_emails_on_sheet):
                print("Error(s) found with Google Sheet formatting. Skipping this Sheet.")
                continue

            # create Collector name and page title and Survey Name
            collector_name = f"Email Invitation for {conductor_name} ({event_title})"  # e.g., Ludovic Morlot (SUB 9)
            survey_name = f"Conductor Evaluation for {conductor_name} ({event_title})"

            # Get appropriate template Survey ID
            template_survey_id = self.get_required_template_survey_id(event_title)
            print("template_survey_id", template_survey_id)


            print("event_title, conductor_name, event_date, number of recipient emails:")
            print(event_title, conductor_name, event_date, f"{len(recipient_emails_on_sheet)} valid emails on sheet")
            print("^ thats from google drive ------------- \n")


            # Get Survey ID for this program, if it exists already. 
            existing_survey_id, _ = self.surveymonkey_client.get_survey_id_by_name(survey_name)

            # Create survey if needed. 
            if not existing_survey_id:
                print("Creating new survey for this program.")
                survey_id = self.surveymonkey_client.clone_survey(template_survey_id, survey_name)
                print("New survey's id: ", survey_id)
            else:
                print(f"Survey '{existing_survey_id}' already exists for this program.")
                survey_id = existing_survey_id

            invite_send_timestamp = self.calculate_distribution_time_for_event_date(event_date)
            close_timestamp = self.calculate_closing_time_for_collector(event_date)

            # Get the collector for this survey, if it exists.
            does_collector_exist, collector_id = self.does_collector_with_this_name_already_exist(survey_id, collector_name)

            # If no collector exists, create it and set the closing time based on the Event Date.
            if not does_collector_exist or not collector_id:
                print(f"Creating new collector on survey. Collector name: '{collector_name}'")
                collector_id, _ = self.surveymonkey_client.create_collector(
                    survey_id, collector_name, close_timestamp
                )

            invite_message_id, reminder_message_id = "", ""

            # if no messages exists, create invite message and reminder message
            messages_on_collector = self.surveymonkey_client.get_messages_on_collector(collector_id)
            print("messages_on_collector", messages_on_collector)

            # if there are 1 or 2 messages, use the existing message id(s)
            if len(messages_on_collector) > 0 and len(messages_on_collector) < 3:
                print(f"{len(messages_on_collector)} message(s) already exist.")
                for message in messages_on_collector:
                    if message["type"] == "invite":
                        invite_message_id = message["id"]
                    if message["type"] == "reminder":
                        reminder_message_id = message["id"]

            # if invite_message_does not exist, create it
            if not invite_message_id:
                print("No invite message exists yet. Creating invite.")
                invite_message_id = self.surveymonkey_client.create_invite_message(collector_id, survey_name)
            # if reminder message does not exist, create reminder.
            if not reminder_message_id:
                print("No reminder message exists yet. Creating reminder.")
                reminder_message_id = self.surveymonkey_client.create_reminder_message(
                    collector_id,
                    subject=f"Reminder: + {survey_name}",
                )

            # throw if we dont have just one invite and one reminder at this point.
            if not invite_message_id or not reminder_message_id or len(messages_on_collector) > 2:
                raise Exception("Invalid message count for survey. Need one invite and one reminder.")

            print("Invite message ID: ", invite_message_id)
            print("Reminder message ID: ", reminder_message_id)

            # update/sync recipients on the INVITE message
            print("Syncing Surveymonkey recipients with Sheet...")
            self.surveymonkey_client.delete_recipients_in_collector_but_not_in_file(collector_id, recipient_emails_on_sheet)
            self.surveymonkey_client.add_recipients(collector_id, invite_message_id, recipient_emails_on_sheet)
            print("Recipients on collector synced with file.")

            # schedule the invite message
            self.surveymonkey_client.schedule_message(collector_id, invite_message_id, invite_send_timestamp)
            # schedule the reminder message
            self.surveymonkey_client.schedule_reminder_message_send(collector_id, reminder_message_id, invite_send_timestamp)

            print(f"Invite, reminder, and recipients synced for survey, '{survey_name}'. Sheet processed.")

            # Move sheet to processed folder
            self.google_sheets_client.move_sheet_to_folder(sheet_id, PROCESSED_FOLDER_ID)
            print(f"{sheet_name} moved to PROCESSED folder.")
        print("No sheets left to process. (: ")

    def is_google_sheet_valid(self, event_title, conductor_name, event_date, recipient_emails_on_sheet):
        errors = []
        if not recipient_emails_on_sheet:
            errors.append("No recipients found on sheet.")
        if not event_title:
            errors.append("Sheet missing event title (e.g. SUB 1).")
        if not conductor_name:
            errors.append("Sheet missing conductor name (e.g. Ludovic Morlot).")
        event_dt = None
        try:
            # Parse as Pacific local time
            pacific = ZoneInfo("America/Los_Angeles")
            event_dt = datetime.strptime(event_date, "%Y-%m-%d %H:%M").replace(tzinfo=pacific)
            # Compare against current UTC time
            now = datetime.now(timezone.utc)
            if event_dt.astimezone(timezone.utc) <= now:
                errors.append(f"Event date {event_dt} must be in the future.")
        except ValueError:
            errors.append(f"Invalid event date format: '{event_date}'. Expected 'YYYY-MM-DD HH:MM'.")
        if errors:
            for e in errors:
                print(e)
            return False
        return True

    def does_collector_with_this_name_already_exist(self, survey_id: str, collector_name: str):
        collector_id, collector_url = self.surveymonkey_client.get_collector_by_name(survey_id, collector_name)
        print("does_collector_with_this_name_already_exist collector_id, collector_url in response:")
        print(collector_id, collector_url)
        if collector_id and collector_url:
            print("A collector for this conductor+program already exists.")
            return True, collector_id
        else:
            return False, None

    def calculate_distribution_time_for_event_date(self, event_date_str: str) -> str:
        # event_date_str expected like '2025-09-16 20:00' in Pacific Time (America/Los_Angeles)
        # Parse naive local time then attach Pacific tzinfo and convert to UTC
        event_dt = datetime.strptime(event_date_str, "%Y-%m-%d %H:%M")
        if ZoneInfo is not None:
            pacific = ZoneInfo("America/Los_Angeles")
            event_dt = event_dt.replace(tzinfo=pacific)
        else:
            # fallback: assume Pacific without DST handling
            event_dt = event_dt.replace(tzinfo=timezone(timedelta(hours=-8)))
        distribution_dt = (event_dt + timedelta(minutes=100)).astimezone(timezone.utc)
        return distribution_dt.isoformat().replace("+00:00", "Z")

    def calculate_closing_time_for_collector(self, event_date_str: str) -> str:
        # Parse event time in Pacific, compute distribution (+100min) then closing (+8 days), return UTC ISO Z
        event_dt = datetime.strptime(event_date_str, "%Y-%m-%d %H:%M")
        if ZoneInfo is not None:
            pacific = ZoneInfo("America/Los_Angeles")
            event_dt = event_dt.replace(tzinfo=pacific)
        else:
            event_dt = event_dt.replace(tzinfo=timezone(timedelta(hours=-8)))
        distribution_dt = (event_dt + timedelta(minutes=100)).astimezone(timezone.utc)
        closing_dt = distribution_dt + timedelta(days=8)
        return closing_dt.isoformat().replace("+00:00", "Z")

    def get_required_template_survey_id(self, event_title: str):
        # TODO polish this?
        print(f"event title is: {event_title}")
        event_title_lowercase = event_title.lower()
        if "opera" in event_title_lowercase:
            return SURVEY_TEMPLATES["Seattle Opera"]
        else:
            return SURVEY_TEMPLATES["SSO"]
