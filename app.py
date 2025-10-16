# -*- coding: utf-8 -*-

# gets list of files from rekordbox and gets track data for each track.
# it then writes track data to a file and uses openai to  get release
# years of tracks and writes in a column next to the year already
# contained in the id3 tag.

# uses rekordbox.xml to get the list of files in the Rekordbox collection.

import sys
import vars
import os
import csv

from openai import OpenAI
from datetime import datetime
from urllib.parse import unquote
from xml.dom import minidom
from tinytag import TinyTag
from mutagen import File
from mutagen.mp4 import MP4
from mutagen.mp3 import MP3
from mutagen.easyid3 import EasyID3
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()


# -----------  Variable Defs  ----------- #

# set paths
rekordbox_xml_file_path = vars.REKORDBOX_XML_FILE_PATH

# set folders to search
search_folders = vars.SEARCH_FOLDERS

# full path to the output files
tracks_csv_file_path = os.path.dirname(__file__) + "/output/tracks.csv"
track_years_csv_file_path = os.path.dirname(
    __file__) + "/output/track-years.csv"


# -----------  Helper Function Defs  ----------- #

# Parse Rekordbox Collection XML
# returns list of track file paths extracted from the rekordbox.xml
def parse_rekordbox_xml(rekordbox_xml, search_folders):
    print("Parsing rekordbox.xml...")

    # list of files (file paths) in the rekordbox collection
    rekordbox_collection_file_path_list = []

    # parse the xml file as DOM
    dom = minidom.parse(rekordbox_xml)

    # get element <COLLECTION>
    collection = dom.getElementsByTagName("COLLECTION")

    # get all elements named <TRACK> (this should be all files in the rekordbox collection)
    tracks = collection[0].getElementsByTagName("TRACK")

    for track in tracks:
        # the element will be URL encoded, so we first need to unencode using the imported unquote function
        url_unencoded_file_path = unquote(track.attributes["Location"].value)

        # now we can remove the "localhost" in the file path string
        file_path = url_unencoded_file_path.replace("file://localhost", "")

        # add track file path to an inclusive list for comparison later
        # ONLY if in music-library dir and ONLY if in the specified folders
        if "music-library" in file_path:
            if search_folders:
                if any(substring in file_path for substring in search_folders):
                    rekordbox_collection_file_path_list.append(file_path)
            else:
                rekordbox_collection_file_path_list.append(file_path)

        rekordbox_collection_file_path_list.sort()

    return rekordbox_collection_file_path_list


# Extract track data from file, given the file path
# returns list of lists [ [file_path, track_title, artist, track_title_formatted, and year] ]
def extract_track_data(track_file_path_list):
    print("Extracting data from parsed rekordbox xml...")

    track_data_list = []

    for file_path in track_file_path_list:
        tag: TinyTag = TinyTag.get(file_path)

        # format existing year to 4 digits
        if tag.year == None:
            year = tag.year

        else:
            if len(tag.year) == 4:
                year = tag.year

            elif len(tag.year) == 10:
                dt = datetime.strptime(tag.year, "%Y-%m-%d")
                year = dt.year

            else:
                dt = datetime.strptime(tag.year, "%Y-%m-%dT%H:%M:%SZ")
                year = dt.year

        # format track title
        track_title_formatted = str(tag.title).replace(
            "(Clean)", "").replace("(Dirty)", "").replace("(Intro)", "").replace("(Intro Clean)", "").replace("(Intro Dirty)", "").replace("(Intro - Clean)", "").replace("(Intro - Dirty)", "").replace("(HH Clean Intro)", "").replace("(HH Dirty Intro)", "").replace("(HH Dirty Mixshow)", "").replace("*", "").strip()

        # create list with [file_path, track_title, artist, track_title_formatted, year]
        track_info = [file_path, str(tag.title), str(
            tag.artist), track_title_formatted, str(year)]

        track_data_list.append(track_info)

    return track_data_list


# Parse csv file and convert data to list of lists
# note: this will remove the 0 index tuple which contains the headers
def parse_csv_to_list(csv_file_path):
    print("Parsing track data from csv file...")

    with open(csv_file_path) as file:
        track_data_list = [line for line in csv.reader(file)]
        # remove the header line ["Location", "Title", "Artist"....]
        track_data_list.pop(0)

    return track_data_list


# Get last line written to the track-years.csv (the point where we left off)
# returns a list of the last processed track data
def get_last_processed_track(track_years_csv_file_path):
    print("Getting last processed track...")

    with open(track_years_csv_file_path, 'r') as file:
        reader = reversed(list(csv.reader(file)))
        last_row = list(next(reader))

    return last_row


# Create list of track data lists based on the last track that was processed
# params: list of the last processed track data, our main track data list
# returns: new track_data_list with only the remaining unprocessed tracks
def create_continuation_track_data_list(last_processed_track, track_data_list):
    print("Creating new track_data_list with remaining unprocessed file paths...")

    idx_of_last_processed_item = [idx for idx,
                                  item in enumerate(track_data_list) if item[0] == last_processed_track[0]][0]

    starting_index = idx_of_last_processed_item + 1

    cont_track_data_list = track_data_list[starting_index:]

    return cont_track_data_list


# Send request for track release year
# returns the possible release year
def search_for_release_year(track_title, artist):
    print("\nSending chatGPT query...")
    response = client.responses.create(
        model="gpt-5-nano",
        input=f"What year was {track_title} by {artist} released?  I only want the 4 digit exact release year."
    )

    if len(response.output_text) == 4:
        possible_release_year = response.output_text
    else:
        print(f"==> Respose malformed for {track_title} by {artist}")
        print(f"==> response: {response.output_text}")
        possible_release_year = 0

    return possible_release_year


# Appends possible year to each track data list item.
# Incrementally writes to csv so if an error occurs, we can restart without
# reprocessing already processed tracks.
# params: list of track data lists, file path to the csv we are writing to
def update_track_data_with_possible_year(track_data_list, track_years_csv_file_path):
    print("Updating track data with possible release years...")

    is_new_file = not (os.path.exists(track_years_csv_file_path))

    # open the file that we will incrementally write to or append to
    file = open(track_years_csv_file_path, "a")

    # write header for csv ONLY if file is new file
    if is_new_file:
        file.write(
            "Location, Track Title, Artist, Track Title Formatted, Year, Possible Year\n")

    for track_data in track_data_list:
        # extract track formatted title and artist from track data tuple
        track_title_formatted = track_data[3]
        artist = track_data[2]

        # send inquiry to chatGPT
        possible_release_year = search_for_release_year(
            track_title_formatted, artist)

        # add possible release year to track data
        track_data.append(possible_release_year)

        # extra check to make sure the data going into our list is properly
        # formatted. there should be only 6 items in the track data list item.
        if (len(track_data) > 6):
            print("==> Malformed track data detected: ", track_data)
            raise ValueError(
                "Track data list item contains more entries than it is supposed to.")

        # write new line to csv file containing updated track data
        writer = csv.writer(file, quoting=csv.QUOTE_ALL)
        writer.writerow(track_data)

    # close the file
    file.close()


# Output results to file.  will overwrite existing files
# Always writes header to first line
def output_to_csv(track_data_list, filename):
    print("Writing data to csv file...")

    # write our outputs to the file with our filename arg
    file = open(
        f"/Users/jasontakahashi/Documents/Jaytee/Projects/my-projects/song-years/output/{filename}.csv", "w")

    file.write(
        "Location, Track Title, Artist, Track Title Formatted, Year\n")

    for item in track_data_list:
        writer = csv.writer(file, quoting=csv.QUOTE_ALL)
        writer.writerow(item)

    # close the file
    file.close()


# -----------  Get Track Release Years  ----------- #

def get_track_release_year(tracks_csv_file_path, track_years_csv_file_path, rekordbox_xml_file_path, search_folders):
    # if tracks.csv exists, then we are continuing an error'd out or cancelled
    # operation so we can check the track-years csv file and parse the remaining
    # unprocessed tracks to create a new track_data_list and pass it to the
    # update_track_data func and avoid parsing the rekordbox xml again or
    # re-searching already processed tracks
    if (os.path.exists(tracks_csv_file_path)):
        proceed = input(
            "track-years.csv file exists. Continue track year updating? (y/n) ")

        if proceed.lower == "y":
            print("Continuing getting track years...")

            orig_track_data_list = parse_csv_to_list(tracks_csv_file_path)

            last_processed_track = get_last_processed_track(
                track_years_csv_file_path)

            cont_track_data_list = create_continuation_track_data_list(
                last_processed_track, orig_track_data_list)

            # optional: write our continuation track list to a new file
            output_to_csv(cont_track_data_list, "tracks-continued")

            update_track_data_with_possible_year(
                cont_track_data_list, track_years_csv_file_path)

            print("Finished track year updating.")
            exit()

        else:
            print("Quitting script...")
            exit()

    # starting a fresh operation with not tracks.csv present
    else:
        # ensure user has exported a current version of the Rekordbox.xml
        proceed = input(
            "The rekordbox.xml file must be current or data will be incorrect. Continue? (y/n) ")

        if proceed.lower() == "y":
            rekordbox_collection_files = parse_rekordbox_xml(
                rekordbox_xml_file_path, search_folders)

            track_data_list = extract_track_data(rekordbox_collection_files)

            # write our track data list to file
            output_to_csv(track_data_list, "tracks")

            update_track_data_with_possible_year(
                track_data_list, track_years_csv_file_path)

        else:
            print("Quitting script...")
            exit()


# -----------  Fix Malformed Data  ----------- #

# data could have been malformed by bad csv writes where
# commas were a part of the track file path or artist entry.
# this finds and fixes it using the correct csv.writeline method
def fix_malformed_data(tracks_csv_file_path, track_years_csv_file_path):
    track_years_data_list = parse_csv_to_list(track_years_csv_file_path)
    tracks_data_list = parse_csv_to_list(tracks_csv_file_path)

    for idx, item in enumerate(track_years_data_list):
        # # get index of malformed data which is any tuple longer than 6
        # if len(item) > 6:
        #     # this is the line we will replace in the track-years.csv (data is broken on this line)
        #     broken_data = track_years_data_list[idx]
        #     print(broken_data)

        #     # this is the item that will be inserted -  coming from tracks.csv (data is still in tact)
        #     correct_data = tracks_data_list[idx]

        #     possible_year = search_for_release_year(
        #         correct_data[3], correct_data[2])

        #     correct_data = correct_data.append(possible_year)

        #     track_years_data_list[idx] = correct_data

        # -----------------------------------------------------#

        # this is the line we will replace in the track-years csv (data is broken on this line)
        broken_data = item
        possible_year = broken_data[5]
        print(broken_data)

        # this is the item that will be inserted -  coming from tracks.csv (data is still in tact)
        correct_data = tracks_data_list[idx]

        # add the possible year from the tracks_years_data_list to the correct data
        correct_data.append(possible_year)
        print(correct_data)

        track_years_data_list[idx] = correct_data

    output_to_csv(track_years_data_list, "track-years")


# -----------  Fix Missing Track Years  ----------- #

# chatGPT may have not retured a release year.  it this case
# the entered year is "0".  this func re-queries those entries.
def fix_missing_years(track_years_csv_file_path):
    track_years_data_list = parse_csv_to_list(track_years_csv_file_path)

    # missing_years_track_list will be a list of nested tuples:
    # [ tuple( index in track_years_data_list, [track_data] ) ]
    missing_years_track_list = [
        (idx, item) for idx, item in enumerate(track_years_data_list) if item[5] == "0"]

    proceed = input(
        f"There are {len(missing_years_track_list)} tracks that need to be rechecked.  Would you like to continue? (y/n): ")

    if proceed.lower() == "y":

        # loop through each item, get the year again, and replace the
        # item in our main_track_years_data_list with the updated item
        for (idx_in_track_years_list, track_data_item) in missing_years_track_list:
            artist = track_data_item[2]
            formatted_track_name = track_data_item[3]

            possible_year = search_for_release_year(
                formatted_track_name, artist)

            # add possible_year to track data
            track_data_item.append(str(possible_year))

            # replace the current track_data_item in the track_data_list with updated track_data_item
            track_years_data_list[idx_in_track_years_list] = track_data_item

        # write updated data to csv
        output_to_csv(track_years_data_list, "track-years")

    else:
        print("Quitting script...")
        exit()


# -----------  Write Results to ID3 Tag  ----------- #

# gets the file type so that mutagen can handle properly
def get_file_format(file_path):
    if (os.path.exists(file_path)):
        audio = File(file_path)
        if audio is not None:
            return audio.mime[0]  # Returns the MIME type
        return "Unknown format"
    else:
        return None


# gets the current year based on file type
# returns current year or None
def get_year(file_path, file_mime_type):
    if file_mime_type == "audio/mp4":
        return MP4(file_path).tags.get("\xa9day", [None])[-1]

    elif file_mime_type == "audio/mp3":
        audio = EasyID3(file_path)
        return audio["date"]

    else:
        print("Audio format unknown")
        return None


# sets the current year based on file type
def set_year(file_path, year, file_mime_type):
    if file_mime_type == "audio/mp4":
        tags = MP4(file_path).tags
        tags["\xa9day"] = year
        tags.save(file_path)

    elif file_mime_type == "audio/mp3":
        audio = EasyID3(file_path)
        audio["date"] = year
        audio.save()

    else:
        print("Cannot set year for this audio format.")


# writes the year to ID3 tag based on the file type and
# updates entry in the track data list for rewriting to
# csv so we know what years have been updated
# (matching years no longer need processing)
def write_tag_based_on_file_type_and_update_track_data_list(track_data_list, idx_in_track_data_list, track_data_item):
    file_path = track_data_item[0]
    found_year = track_data_item[5]

    file_type = get_file_format(file_path)

    if file_type == None:
        print(
            f"{file_path} doesn't exist, please check for errors. skipping...")

    elif file_type == "Unknown format":
        print(
            "Current track is of unknown format, will not attempt to write year...skipping")

    elif file_type == "audio/mp3" or file_type == "audio/mp4":
        print(
            f"Current track is of \"{file_type}\" format. Writing \"{found_year}\" to ID3 tag...")

        set_year(file_path, found_year, file_type)

        # after setting year, update the current track_data_item with the new year
        track_data_item[4] = found_year
        # set the track_data_item in the track_data_list to the updated track_data_item
        track_data_list[idx_in_track_data_list
                        ] = track_data_item

    else:
        print(
            f"Current track is of \"{file_type}\" format.  Script doesn't account for this file format.")
        print(f"Please contact to developer to add support for this file format.")
        print("Skipping track...")


# write year to ID3 tags for tracks
# type == "missing": tagged year unset, found year is not 0
# type == "differing" tagged year different from found year
def write_track_release_years(track_years_csv_file_path, type):
    track_data_list = parse_csv_to_list(track_years_csv_file_path)

    tracks_to_write = []

    if type == "missing":
        tracks_to_write = [
            (idx, item) for idx, item in enumerate(track_data_list) if (item[4] == "0" or item[4] == "None") and not item[5] == "0"]

        if len(tracks_to_write) == 0:
            print("There are no tracks left to write tags to.  Quitting script...")
            exit()

        proceed = input(
            f"There are {len(tracks_to_write)} tracks that have no release year set, but a potential updated release year.  Would you like to continue and write the new release years to the tracks? (y/n): ")

    if type == "differing":
        tracks_to_write = [
            (idx, item) for idx, item in enumerate(track_data_list) if not item[5] == "0" and not item[4] == item[5]]

        if len(tracks_to_write) == 0:
            print("There are no tracks left to write tags to.  Quitting script...")
            exit()

        proceed = input(
            f"There are {len(tracks_to_write)} tracks that have potential updated release years.  Would you like to continue? (y/n): ")

    if proceed.lower() == "y":
        print("Continuing...")

        for idx_in_track_data_list, item in tracks_to_write:

            # write to id3 tag
            write_tag_based_on_file_type_and_update_track_data_list(
                track_data_list, idx_in_track_data_list, item)

        # write the updated track_data_list to the track_years_csv file
        output_to_csv(track_data_list, "track-years")

    else:
        print("Quitting script...")
        exit()


# -----------  Run App Funcs  ----------- #

if len(sys.argv) == 1:
    print("Please add one of the following args: \"get-years\", \"fix-data\", \"fix-missing-years\", \"write-years\".")
    exit()

if sys.argv[1] == "get-years":
    get_track_release_year(tracks_csv_file_path, track_years_csv_file_path,
                           rekordbox_xml_file_path, search_folders)

elif sys.argv[1] == "fix-data":
    fix_malformed_data(tracks_csv_file_path, track_years_csv_file_path)

elif sys.argv[1] == "fix-missing-years":
    fix_missing_years(track_years_csv_file_path)

elif sys.argv[1] == "write-years":
    if len(sys.argv) < 3:
        print("Please include either \"missing\" or \"differing\" as a second argument.")
        print("==> Add \"missing\" to write tracks where tagged year is unset (missing or None) and found year is not 0.")
        print("==> Add \"differing\" to write tracks where the tagged year is different than the found year.")
        exit()

    if not (sys.argv[2] == "missing" or sys.argv[2] == "differing"):
        print(f"\"{sys.argv[2]}\" is not a valid argument.")
        print("Please include either \"missing\" or \"differing\" as a second argument.")
        print("==> Add \"missing\" to write tracks where tagged year is unset (missing or None) and found year is not 0.")
        print("==> Add \"differing\" to write tracks where the tagged year is different than the found year.")
        exit()

    write_track_release_years(track_years_csv_file_path, sys.argv[2])

else:
    print(f"Please add one of the following args when running script: \"get-years\", \"fix-data\", \"fix-missing-years\", \"write-years\".")
    exit()
