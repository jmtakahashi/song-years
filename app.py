# -*- coding: utf-8 -*-

# gets list of files from rekordbox and checks the "Year" tag.
# it then compares the year to the year listed in a music api
# and notes whether year is correct, or different

# uses rekordbox.xml to get the list of files in the Rekordbox collection.

import vars
# import requests
import json

from xml.dom import minidom
from urllib.parse import unquote
from tinytag import TinyTag
from datetime import datetime

# set paths
rekordbox_xml = vars.REKORDBOX_XML
# music_library = vars.MUSIC_LIBRARY_DIR

# set folders to search
search_folders = ["alt-rock", "hiphop", "reggae", "rnb", "top40"]


# ensure user has exported a current version of the Rekordbox.xml
print("The rekordbox.xml file must be current or data will be incorrect.")
input("If the rekordbox.xml file is current, press Enter to continue...")


# -----------  Parse Rekordbox Collection XML  ----------- #

print("Parsing rekordbox.xml...")

# list of files (file paths) in the rekordbox collection
rekordbox_collection_files = []

# parse the xml file as DOM
dom = minidom.parse(rekordbox_xml)

# get element <COLLECTION>
collection = dom.getElementsByTagName('COLLECTION')

# get all elements named <TRACK> (this should be all files in the rekordbox collection)
tracks = collection[0].getElementsByTagName('TRACK')

for track in tracks:
    str_to_replace = "file://localhost"

    # the element will be URL encoded, so we first need to unencode using the imported unquote function
    url_unencoded_location_path = unquote(track.attributes['Location'].value)

    # now we can replace/remove the uneccesary chars in the file path string
    file_path = url_unencoded_location_path.replace(str_to_replace, "")

    # add track file path to an inclusive list for comparison later ONLY if in music-library dir
    # and in the the search_folders array
    if "music-library" in file_path:
        if any(substring in file_path for substring in search_folders):
            rekordbox_collection_files.append(file_path)

    rekordbox_collection_files.sort()


# -----------  Get Track Years from ID3 Tag and check API for possible match ----------- #

print("Getting year data from ID3 tags...")

track_data_list = []

for file_path in rekordbox_collection_files:
    tag: TinyTag = TinyTag.get(file_path)

    if tag.year == None:
        year = tag.year
    else:
        if len(tag.year) == 4:
            year = tag.year
        elif len(tag.year) == 10:
            dt = datetime.strptime(tag.year, '%Y-%m-%d')
            year = dt.year

        else:
            dt = datetime.strptime(tag.year, '%Y-%m-%dT%H:%M:%SZ')
            year = dt.year

    # create our search string
    title_for_search_string = str(tag.title).replace(
        "(Clean)", "").replace("(Dirty)", "").replace("(Intro)", "").replace("(Intro Clean)", "").replace("(Intro Dirty)", "").replace("(Intro - Clean)", "").replace("(Intro - Dirty)", "").replace("(HH Clean Intro)", "").replace("(HH Dirty Intro)", "").replace("(HH Dirty Mixshow)", "").strip()

    # -----------  Send Request to API Using Search String ----------- #
    # response_API = requests.get(
    #     'https://api.covid19india.org/state_district_wise.json')
    # data = response_API.text
    # json.loads(data)
    # # print(response_API.status_code)

    # set tuple with track filepath, title, artist, search string and year
    track_info = ('"' + file_path + '"',
                  '"' + str(tag.title) + '"',
                  '"' + str(tag.artist) + '"',
                  '"' + title_for_search_string + ' ' + str(tag.artist) +
                  ' ' + 'release year' + '"',
                  year)

    track_data_list.append(track_info)


# -----------  Output to File  ----------- #

print("Writing data to csv file...")

# write our outputs to the track-years.txt file
song_years = open(
    "/Users/jasontakahashi/Documents/Jaytee/Projects/my-projects/song-years/output/track-years.csv", "w")

song_years.write("Location, Title, Artist, Search String, Year\n")

for t in track_data_list:
    song_years.write(",".join(str(data) for data in t) + '\n')

# close the file
song_years.close()
