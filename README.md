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
`$ python3 app.py`


