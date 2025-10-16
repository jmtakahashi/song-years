# song years python app

an app to get the release year of tracks in your Rekordbox collection.

uses the rekordbox.xml file that is exported from Rekordbox.

currently uses the openAI gpt-5-nano module to search release years.

## Required

This app requires an openai api key to run.

## Setup

Clone the git hub repo and cd into the folder.  The run the following commands.

Set up a virtual env and install the required deps.

`$ python3 -m venv venv`

`$ source venv/bin/activate`

`$ pip install -r requirement.txt`

Create the required env and vars files

`$ touch vars.py`

`$ touch .env`


### vars.py
holds values particular to each user.

- `REKORDBOX_XML_FILE_PATH` - the full path to your rekordbox.xml file
- `SEARCH_FOLDERS` - if your music library is organized into folders, add the folders names you want to search in python list format ["folder_name", "folder_name"]

### .env

- `OPENAI_API_KEY` - your api key from openai

## Run the app
`$ source venv/bin/activate`

`$ python3 app.py arg1 [arg2]`

`arg1` is required and can be "get-years", "fix-data", "fix-missing-years" or "write-years"

if `arg1` is "write-years" then a second arg of either "missing" or "differing" is required

- "missing" will write year to ID3 tags of tracks where the current tagged year is unset (missing or None) and a found year exists.

- "differing" will write year to ID3 tags of tracks where the currently tagged year is different than the found year.  The found year will overwrite the current year.


