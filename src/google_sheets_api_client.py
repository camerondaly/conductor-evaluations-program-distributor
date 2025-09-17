# sheets_reader.py
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build


class GoogleSheetsApiClient:
    def __init__(self):
        self.creds_file = "google_credentials.json"
        self.SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
        self.gsheet_client = self._authorize_gsheets()
        self.drive_service = self._authorize_drive()
    
    def _authorize_gsheets(self):
        creds = Credentials.from_service_account_file(self.creds_file, scopes=self.SCOPES)
        return gspread.authorize(creds)

    def _authorize_drive(self):
        creds = Credentials.from_service_account_file(self.creds_file, scopes=self.SCOPES)
        return build('drive', 'v3', credentials=creds)

    def read_roster_sheet(self, sheet_id, worksheet_name="Sheet1"):
        """
        Reads the first row for event metadata (title, date, conductor),
        and subsequent rows for recipient emails.
        """
        sh = self.client.open_by_key(sheet_id)
        ws = sh.worksheet(worksheet_name)
        rows = ws.get_all_values()

        # first row has the event data
        event_title = rows[0][0].strip()  # e.g., SUB 9
        conductor_name = rows[0][1].strip()  # e.g., "Ludovic Morlot"
        last_concert_timestamp = rows[0][2].strip()  # e.g., "2025-09-16 20:00"

        # Recipients start from row 2
        emails = []
        for r in rows[1:]:
            if len(r) < 4:
                continue
            email = r[2].strip()
            if email and "@" in email:
                emails.append(email)

        # Add the librarians
        emails.append("Olivia.sangiovese@gmail.com")
        emails.append("carledwardwilder@gmail.com")

        return event_title, conductor_name, last_concert_timestamp, emails
    
    def move_sheet_to_folder(self, sheet_id, folder_id):
        """
        Moves a Google Sheet to a different Drive folder.
        """
        # Get current parents
        file = self.drive_service.files().get(fileId=sheet_id, fields='parents').execute()
        previous_parents = ",".join(file.get('parents', []))

        # Move file to new folder
        self.drive_service.files().update(
            fileId=sheet_id,
            addParents=folder_id,
            removeParents=previous_parents,
            fields='id, parents'
        ).execute()

    def list_sheets_in_folder(self, folder_id):
        """
        List all Google Sheets in a Drive folder.
        Returns list of tuples: (sheet_id, sheet_name)
        """
        query = f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.spreadsheet' and trashed=false"
        sheets = []
        page_token = None

        while True:
            response = self.drive_service.files().list(
                q=query,
                spaces='drive',
                fields='nextPageToken, files(id, name)',
                pageToken=page_token
            ).execute()

            for file in response.get('files', []):
                sheets.append((file['id'], file['name']))

            page_token = response.get('nextPageToken')
            if not page_token:
                break

        return sheets

# Sheet layout
"""
| Row | Event Title / Conductor | Conductor Name | Event Date (YYYY-MM-DD HH:MM)  | First Name | Last Name | Email                                                     | Instrument |
| --- | ----------------------- | -------------- | ------------------------------ | ---------- | --------- | --------------------------------------------------------- | ---------- |
| 1   | SUB 9.                  | Jane Doe       | 2025-09-16 20:00               |            |           |                                                           |            |
| 2   |                         |                |                                | Jacqueline | Audas     | [jaudas@icloud.com](mailto:jaudas@icloud.com)             | Violin 1   |
| 3   |                         |                |                                | Jennifer   | Bai       | [yubaiviolin@yahoo.com](mailto:yubaiviolin@yahoo.com)     | Violin 1   |
| 4   |                         |                |                                | Timothy    | Garland   | [garlandviolin@gmail.com](mailto:garlandviolin@gmail.com) | Violin 1   |
...

"""
