# song years python app

an app to get the release year of track.

uses the rekordbox.xml file that is exported from Rekordbox.

currently uses the openAI gpt-5-nano module to search release years.

## Setup

Clone the git hub repo and cd into the folder.  The run the following commands.

Set up a virtual env

`$ python3 -m venv venv`

Install the required dependancies.

`$ pip install -r requirement.txt`

Create the required env and vars files

`$ touch vars.py`

`$ touch .env`


### vars.py
holds values independant of each user.

- `REKORDBOX_XML` - the full path to your rekordbox.xml file
- `SEARCH_FOLDERS` - if your music library is organized into folders, add the folders names you want to search in python list format ["folder_name", "folder_name"]

### .env

- `OPENAI_API_KEY` - your api key from open ai

## Run the app

at bottom of the `app.py` uncomment the function you want to run, save, then

`$ python3 app.py`


