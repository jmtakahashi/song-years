#!/usr/bin/env python
# -*- coding: utf-8 -*-

# gets list of files from rekordbox and gets track data for each track.
# it then writes track data to a file and uses openai to  get release
# years of tracks and writes in a column next to the year already
# contained in the id3 tag.

# uses rekordbox.xml to get the list of files in the Rekordbox collection.

import vars
import os
import csv
import regex

import pyfiglet
from termcolor import colored

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
    """
    Parses a rekordbox.xml file and extracts the file paths
    into a list.  Returns the list of filepaths.
    """
    print(colored("Parsing rekordbox.xml...", color="white"))

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
# returns list of track data [file_path, track_title, artist, track_title_formatted, and year]
def extract_track_data(track_file_path):
    """
    Gets the track information from the track's metadata tags.
    """

    print(colored(f"Processing {track_file_path}...", color="white"))

    tag: TinyTag = TinyTag.get(track_file_path)

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
    track_data_item = [track_file_path, str(tag.title), str(
        tag.artist), track_title_formatted, str(year)]

    # extra check to make sure the data going into our list is properly
    # formatted. there should be only 5 items in the track data list item.
    if (len(track_data_item) > 5):
        print(colored("==> Malformed track data detected: " +
              str(track_data_item), color="magenta"))
        raise ValueError(
            "Track data list item contains more entries than it is supposed to.")

    return track_data_item


# Parse csv file and convert data to list of lists
# note: this will remove the 0 index tuple which contains the headers
def parse_csv_to_list(csv_file_path):
    """
    Converts a csv file to a list of track data items.
    Track data items are also a list of the tracks data.
    """
    print(colored("Parsing track data from csv file...", color="white"))

    with open(csv_file_path) as file:
        track_data_list = [line for line in csv.reader(file)]
        # remove the header line ["Location", "Title", "Artist"....]
        track_data_list.pop(0)

    return track_data_list


# Get last line written to the track-years.csv (the point where we left off)
# returns a list of the last processed track data [file_path, track_title, artist, track_title_formatted, year, possible_year]
def get_last_processed_track(track_years_csv_file_path):
    """
    Given a csv filpath, returns the last line of the file.
    """
    print(colored("Getting last processed track...", color="white"))

    with open(track_years_csv_file_path, 'r') as file:
        reader = reversed(list(csv.reader(file)))
        last_row = list(next(reader))

    return last_row


# Create list of track data lists based on the last track that was processed
# params: list of the last processed track data, our main track data list
# returns: new track_data_list with only the remaining unprocessed tracks
def create_continuation_track_data_list(last_processed_track, track_data_list):
    """
    Creates a list of remaining track data items for us to process.
    """
    print(colored("Creating new track_data_list with remaining unprocessed file paths...", color="white"))

    idx_of_last_processed_item = [idx for idx,
                                  item in enumerate(track_data_list) if item[0] == last_processed_track[0]][0]

    starting_index = idx_of_last_processed_item + 1

    cont_track_data_list = track_data_list[starting_index:]

    return cont_track_data_list


# Send request for track release year
# returns the possible release year or 0
def search_for_release_year(track_title, artist, set_year):
    """
    Sends a query for the 4 digit track year.
    """
    print(colored(
        f"\nSending chatGPT query for {track_title} by {artist}...", color="white"))

    response = client.responses.create(
        model="gpt-5-nano",
        input=f"What year was {track_title} by {artist} released?  Please return only exact 4 digit exact release year."
    )

    if len(response.output_text) == 4:
        return response.output_text
    else:
        print(
            colored(f"==> Response not a 4 digit year for {track_title} by {artist}", color="white"))
        print(
            colored(f"==> Chat response: {response.output_text}", color="red"))

        return "0"


# Appends possible year to a track data list item where no possible exists.
# return: updated track data item [file_path, track_title, artist, track_title_formatted, year, found_year]
def update_track_data_with_possible_year(track_data_item, updated_year):
    """
    Updates a track data item with possible release year.
    """

    track_title_formatted = track_data_item[3]
    artist = track_data_item[2]
    set_year = track_data_item[4]

    print(colored(
        f"Updating {track_title_formatted} by {artist} with {updated_year}...", color="white"))

    # add possible release year to track data
    track_data_item[5] = updated_year

    return track_data_item


# Output results to file.  will overwrite existing files
# Always writes header to first line
def output_to_csv(track_data_list, filename):
    """
    Takes a list of track data items and outputs each item to row in a csv file.
    """
    print(colored("Writing data to csv file...", color="white"))

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
        proceed = input(colored(
            "==> track-years.csv file exists. Continue track year updating? (y/n) ", color="magenta"))

        if proceed.lower() == "y":
            print(colored("Continuing getting track years...", color="white"))

            orig_track_data_list = parse_csv_to_list(tracks_csv_file_path)

            last_processed_track = get_last_processed_track(
                track_years_csv_file_path)

            cont_track_data_list = create_continuation_track_data_list(
                last_processed_track, orig_track_data_list)

            if len(cont_track_data_list) < 1:
                print(colored("No tracks left to process. Quitting...", color="magenta"))
                exit()

            # optional: write our continuation track list to a new file
            output_to_csv(cont_track_data_list, "tracks-continued")

            # open the csv file that we will append to
            file = open(track_years_csv_file_path, "a")

            for track_data_item in cont_track_data_list:
                formatted_track_title = track_data_item[3]
                artist = track_data_item[2]

                found_year = search_for_release_year(
                    formatted_track_title, artist)

                track_data = update_track_data_with_possible_year(
                    track_data_item, found_year)

                # Incrementally writes to csv so if an error occurs,
                # we can restart without reprocessing already processed tracks.
                writer = csv.writer(file, quoting=csv.QUOTE_ALL)
                writer.writerow(track_data)

            # close the file
            file.close()

            print(colored("Finished getting track years.  Exiting...", color="white"))
            exit()

        else:
            print(colored("Quitting script...", color="magenta"))
            exit()

    # starting a fresh operation with tracks.csv not present
    else:
        # ensure user has exported a current version of the Rekordbox.xml
        proceed = input(colored(
            "The rekordbox.xml file must be current or data will be incorrect. Continue? (y/n) ", color="cyan"))

        if proceed.lower() == "y":
            rekordbox_collection_files = parse_rekordbox_xml(
                rekordbox_xml_file_path, search_folders)

            print(colored("Extracting data from parsed rekordbox xml...", color="white"))

            track_data_list = []
            for file_path in rekordbox_collection_files:
                track_data = extract_track_data(file_path)
                track_data_list.append(track_data)

            # write our track data list to file
            output_to_csv(track_data_list, "tracks")

            # create the file that we will incrementally write to
            file = open(track_years_csv_file_path, "w")

            # write header for csv since this is a going to be a fresh write
            file.write(
                "Location, Track Title, Artist, Track Title Formatted, Year, Possible Year\n")

            for track_data_item in track_data_list:
                formatted_track_title = track_data_item[3]
                artist = track_data_item[2]

                found_year = search_for_release_year(
                    formatted_track_title, artist)
                track_data = update_track_data_with_possible_year(
                    track_data_item, found_year)

                # Incrementally writes to csv so if an error occurs,
                # we can restart without reprocessing already processed tracks.
                writer = csv.writer(file, quoting=csv.QUOTE_ALL)
                writer.writerow(track_data)

            # close the file
            file.close()

            print(colored("Finished getting track years.  Exiting...", color="white"))
            exit()

        else:
            print(colored("Quitting script...", color="magenta"))
            exit()


# -----------  Fix Missing Track Years  ----------- #

# chatGPT may have not retured a release year.  it this case
# the entered year is "0".  this func re-queries those entries.
# and alternatively allows user to enter their own found year.
def fix_missing_years(track_years_csv_file_path):
    track_years_data_list = parse_csv_to_list(track_years_csv_file_path)

    # missing_years_track_list will be a list of nested tuples:
    # [ tuple( index in track_years_data_list, [track_data] ) ]
    missing_years_track_list = [
        (idx, item) for idx, item in enumerate(track_years_data_list) if item[5] == "0"]

    proceed = input(colored(
        f"There are {len(missing_years_track_list)} tracks that need to be rechecked.  Would you like to continue? (y/n): ", color="cyan"))

    if proceed.lower() == "y":

        # loop through each item, get the year again, and replace the
        # item in our main_track_years_data_list with the updated item
        for (idx_in_track_years_list, track_data_item) in missing_years_track_list:
            artist = track_data_item[2]
            formatted_track_name = track_data_item[3]
            set_year = track_data_item[4]

            print(
                colored(f"\nNext track to query for: {formatted_track_name} by {artist} with set year {set_year}", color="white"))

            user_response = None
            user_entered_year = None
            year_to_add = None

            while True:
                user_response = input(colored(
                    "Enter \"run\" to query, enter your own 4 digit year, press the return button to skip this track, or enter \"quit\" to exit: ", color="cyan"))

                if user_response.lower() in ["run", "quit", "", ]:
                    break

                if regex.match(r"(?:19|20)\d{2}", user_response):
                    year_to_add = user_response
                    break

            if user_response.lower() == "quit":
                break

            if user_response == "":
                print(colored("Skipping current track...", color="magenta"))
                continue

            if user_response.lower() == "run":
                found_year = search_for_release_year(
                    formatted_track_name, artist, set_year)

                if found_year == "0":
                    print(colored("Skipping current track...", color="magenta"))
                    break

                year_to_add = found_year

            # replace "missing" year with user-entered year
            track_data_item = update_track_data_with_possible_year(
                track_data_item, year_to_add)

            # replace the current track_data_item in the track_data_list with updated track_data_item
            track_years_data_list[idx_in_track_years_list] = track_data_item

        # write updated data to csv
        output_to_csv(track_years_data_list, "track-years")

    else:
        print(colored("Quitting script...", color="magenta"))
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
        return None  # for files that don't exist


# gets the current year based on file type
# returns current year or None
def get_year(file_path, file_mime_type):
    if file_mime_type == "audio/mp4":
        return MP4(file_path).tags.get("\xa9day", [None])[-1]

    elif file_mime_type == "audio/mp3":
        audio = EasyID3(file_path)
        return audio["date"]

    else:
        print(colored("Audio format unknown", color="magenta"))
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
        print(colored("Cannot set year for this audio format.", color="magenta"))


# write year to ID3 tags
# type == "missing": tagged year unset, found year is not 0
# type == "differing" tagged year different from found year
def write_track_release_years(track_years_csv_file_path, type):
    track_data_list = parse_csv_to_list(track_years_csv_file_path)

    tracks_to_write = []
    proceed = None

    if type == "missing":
        tracks_to_write = [
            (idx, item) for idx, item in enumerate(track_data_list) if (item[4] == "0" or item[4] == "None") and not item[5] == "0"]

        if len(tracks_to_write) == 0:
            print(colored(
                "There are no tracks left to write tags to.  Quitting script...", color="magenta"))
            exit()

        proceed = input(colored(
            f"There are {len(tracks_to_write)} tracks that have no release year set, but a potential updated release year.  Would you like to continue and write the new release years to the tracks? (y/n): ", color="cyan"))

    if type == "differing":
        tracks_to_write = [
            (idx, item) for idx, item in enumerate(track_data_list) if not item[5] == "0" and not item[4] == item[5]]

        if len(tracks_to_write) == 0:
            print(colored(
                "There are no tracks left to write tags to.  Quitting script...", color="magenta"))
            exit()

        proceed = input(colored(
            f"There are {len(tracks_to_write)} tracks that have potential updated release years.  Would you like to continue? (y/n): ", color="cyan"))

    if proceed.lower() == "y":
        print(colored("Continuing...", color="white"))

        for idx_in_track_data_list, track_data_item in tracks_to_write:
            file_path = track_data_item[0]
            found_year = track_data_item[5]

            file_type = get_file_format(file_path)

            if file_type == None:
                print(colored(
                    f"{file_path} doesn't exist, please check for errors. skipping...", color="magenta"))

            elif file_type == "Unknown format":
                print(colored(
                    "Current track is of unknown format, will not attempt to write year...skipping", color="magenta"))

            elif file_type == "audio/mp3" or file_type == "audio/mp4":
                print(colored(
                    f"Current track is of \"{file_type}\" format. Writing \"{found_year}\" to ID3 tag...", color="white"))

                set_year(file_path, found_year, file_type)

                # after setting year in ID3 tag, update the current track_data_item with the new year
                track_data_item[4] = found_year

                # set the track_data_item in the track_data_list to the updated track_data_item
                track_data_list[idx_in_track_data_list
                                ] = track_data_item

            else:
                print(colored(
                    f"Current track is of \"{file_type}\" format.  This script doesn't account for this file format.", color="magenta"))
                print(colored(
                    f"Please contact the developer to add support for this file format.", color="magenta"))
                print(colored("Skipping track...", color="magenta"))

        # write the updated track_data_list to the track_years_csv file
        output_to_csv(track_data_list, "track-years")

    else:
        print(colored("Quitting script...", color="magenta"))
        exit()


# -----------  Run App  ----------- #

def main(rekordbox_xml_file_path, search_folders, tracks_csv_file_path, track_years_csv_file_path):
    print(colored(pyfiglet.figlet_format(
        "Track Release Years", font="slant"), color="cyan"))
    print(colored(
        "<----------------- by https://whoisjaytee.com ----------------->\n", color="white"))

    function_to_run = ""

    while not function_to_run.lower() in ["1", "2", "3", "q"]:
        print(colored("Please enter a number to start:", color="cyan"))
        function_to_run = input(colored(
            "=> \"1\" to get all track years\n=> \"2\" to fix missing track years\n=> \"3\" to write track years to meta tags\n=> or type \"q\" to exit.\nYour choice: ", color="white"))

    if function_to_run == "1":
        proceed = input(
            colored("\"1. Get all track years\" entered. Ok to proceed? (y/n): ", color="cyan"))
        if proceed.lower() == "y":
            get_track_release_year(tracks_csv_file_path, track_years_csv_file_path,
                                   rekordbox_xml_file_path, search_folders)
        else:
            print(colored("Quitting script...", color="magenta"))
            exit()

    elif function_to_run == "2":
        proceed = input(colored(
            "\"2. Get missing track years\" entered. Ok to proceed? (y/n): ", color="cyan"))
        if proceed.lower() == "y":
            fix_missing_years(track_years_csv_file_path)
        else:
            print(colored("Quitting script...", color="magenta"))
            exit()

    elif function_to_run == "3":
        print(colored(
            f"\"3. Write track years to meta data\" entered. Please enter one of the following:", color="cyan"))
        print(colored("==> \"1\" to write tracks where tagged year is unset (missing or None) and found year is not 0.", color="white"))
        print(colored(
            "==> \"2\" to write tracks where the tagged year is different than the found year.", color="white"))

        type_of_years = ""

        while not type_of_years.lower() in ["1", "2", "q"]:
            type_of_years = input(colored(
                "Please enter either \"1\" or \"2\" or type \"q\" to exit: ", color="cyan"))

        if type_of_years == "1":
            proceed = input(
                colored("\"1 - write missing years\" entered. Ok to proceed? (y/n): ", color="cyan"))

            if proceed.lower() == "y":
                write_track_release_years(
                    track_years_csv_file_path, "missing")
            else:
                print(colored("Quitting script...", color="magenta"))
                exit()

        if type_of_years == "2":
            proceed = input(
                colored("\"2 - write differing years\" entered. Ok to proceed? (y/n): ", color="cyan"))

            if proceed.lower() == "y":
                write_track_release_years(
                    track_years_csv_file_path, "differing")
            else:
                print(colored("Quitting script...", color="magenta"))
                exit()

        else:
            print(colored("Quitting script...", color="magenta"))
            exit()

    else:
        print(colored("Quitting script...", color="magenta"))
        exit()


if __name__ == "__main__":
    main(rekordbox_xml_file_path, search_folders,
         tracks_csv_file_path, track_years_csv_file_path)
