# -*- coding: utf-8 -*-

# gets list of files from rekordbox and gets track data for each track.
# it then writes track data to a file and uses openai to  get release
# years of tracks and writes in a column next to the year already
# contained in the id3 tag.

# uses rekordbox.xml to get the list of files in the Rekordbox collection.

import vars
import os
import csv

from openai import OpenAI
from datetime import datetime
from urllib.parse import unquote
from xml.dom import minidom
from tinytag import TinyTag
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()


# -----------  Variable defs  ----------- #

# set paths
rekordbox_xml = vars.REKORDBOX_XML

# set folders to search
search_folders = vars.SEARCH_FOLDERS

# if restarting after an error, are there existing csv's
tracks_csv_filepath = vars.TRACKS_CSV_FILEPATH
track_years_csv_filepath = tracks_csv_filepath.replace(
    "tracks.csv", "track-years.csv")


# -----------  Function defs  ----------- #

# Parse Rekordbox Collection XML
# returns list of track file paths extracted from the rekordbox.xml
def parse_rekordbox_xml(rekordbox_xml, search_folders):
    print("Parsing rekordbox.xml...")

    # list of files (file paths) in the rekordbox collection
    rekordbox_collection_file_list = []

    # parse the xml file as DOM
    dom = minidom.parse(rekordbox_xml)

    # get element <COLLECTION>
    collection = dom.getElementsByTagName('COLLECTION')

    # get all elements named <TRACK> (this should be all files in the rekordbox collection)
    tracks = collection[0].getElementsByTagName('TRACK')

    for track in tracks:
        str_to_replace = "file://localhost"

        # the element will be URL encoded, so we first need to unencode using the imported unquote function
        url_unencoded_location_path = unquote(
            track.attributes['Location'].value)

        # now we can replace/remove the uneccesary chars in the file path string
        file_path = url_unencoded_location_path.replace(str_to_replace, "")

        # add track file path to an inclusive list for comparison later ONLY if in music-library dir
        # and in the the search_folders array
        if "music-library" in file_path:
            if any(substring in file_path for substring in search_folders):
                rekordbox_collection_file_list.append(file_path)

        rekordbox_collection_file_list.sort()

    return rekordbox_collection_file_list


# Extract track data from file and use to search
# returns list of tuples [ (filepath, track_title, artist, track_title_formatted, and year) ]
def extract_track_data(track_filepath_list):
    print("Extracting data from parsed rekordbox xml...")

    track_data_list = []

    for file_path in track_filepath_list:
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

        # format track title
        track_title_formatted = str(tag.title).replace(
            "(Clean)", "").replace("(Dirty)", "").replace("(Intro)", "").replace("(Intro Clean)", "").replace("(Intro Dirty)", "").replace("(Intro - Clean)", "").replace("(Intro - Dirty)", "").replace("(HH Clean Intro)", "").replace("(HH Dirty Intro)", "").replace("(HH Dirty Mixshow)", "").replace("*", "").strip()

        # create tuple with track filepath, track_title, artist, track_title_formatted and year
        track_info = ('"' + file_path + '"',
                      '"' + str(tag.title) + '"',
                      '"' + str(tag.artist) + '"',
                      '"' + track_title_formatted + '"',
                      year)

        track_data_list.append(track_info)

    return track_data_list


# Parse csv file and convert data to list of tuples
def parse_csv_to_tuple_list(csv_file):
    print("Parsing track data from tracks.csv...")

    with open(csv_file) as f:
        track_data_list = [tuple(line) for line in csv.reader(f)]
        track_data_list.pop(0)

    return track_data_list


# Get last line written to the track-years.csv (the point where we left off)
# returns a tuple of the last processed track data
def get_last_processed_track(track_years_csv_filepath):
    print("Getting last processed track...")

    with open(track_years_csv_filepath, 'r') as file:
        reader = reversed(list(csv.reader(file)))
        last_row = next(reader)

    return tuple(last_row)


# Find last parsed track and create list of track data tuples based on that
# args: tuple of the last processed track data, our track data list
# returns an edited track_data_list with only the remaining unprocessed items
def create_continuation_track_data_list(last_processed_track, track_data_list):
    print("Creating new track_data_list with remaining unprocessed filepaths...")

    idx_of_last_processed_item = [idx for idx,
                                  item in enumerate(track_data_list) if item[0] == last_processed_track[0]][0]

    cont_track_data_list = track_data_list[idx_of_last_processed_item + 1:]

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
        print(f"Year malformed for {track_title} by {artist}")
        print(f"==> response: {response.output_text}")
        possible_release_year = 0

    return possible_release_year


# Updates list of track data tuples with the possible year
# accepts a list of tuples (from memory) as params
# incrementally writes to a file so if an error occurs, we can restart and
# not waste credits with checking files that were already run
def update_track_data_with_possible_year(track_data_list, track_years_csv_filepath):
    print("Updating track data with possible release years...")

    is_new_file = not (os.path.exists(track_years_csv_filepath))

    # open the file that we will incrementally write to or append to
    file = open(track_years_csv_filepath, "a")

    # write header for csv ONLY if file is new file
    if is_new_file:
        file.write(
            "Location, Track Title, Artist, Track Title Formatted, Year, Possible Year\n")

    for track_data_tuple in track_data_list:
        # extract track formatted title and artist from track data tuple
        track_title_formatted = track_data_tuple[3]
        artist = track_data_tuple[2]

        possible_release_year = search_for_release_year(
            track_title_formatted, artist)

        track_data_tuple = track_data_tuple + (possible_release_year, )

        # extra check to make sure the data going into our list is
        # properly formatted.  there should be only 6 items.
        if (len(track_data_tuple) > 6):
            print("==> Malformed data: " + track_data_tuple)
            raise ValueError(
                "Tuple contains more entries than it is supposed to.")

        # write new line to csv file containing final data
        writer = csv.writer(file, quoting=csv.QUOTE_ALL)
        writer.writerow(track_data_tuple)

    # close the file
    file.close()


# Output results to File.  will overwrite existing files
# writes header to first line
def output_to_csv(tuple_list, filename):
    print("Writing data to csv file...")

    # write our outputs to the file with our passed filename arg
    file = open(
        f"/Users/jasontakahashi/Documents/Jaytee/Projects/my-projects/song-years/output/{filename}.csv", "w")

    file.write(
        "Location, Track Title, Artist, Track Title Formatted, Year\n")

    for t in tuple_list:
        writer = csv.writer(file, quoting=csv.QUOTE_ALL)
        writer.writerow(t)

    # close the file
    file.close()


# -----------  Get Track Release Years  ----------- #

def get_track_release_year():

    # if tracks.csv exists, then we are continuing an error'd out operation
    # so we can use the track-years csv file and parse the remaining unprocessed
    # tracks to create a track_data_list and pass it to our update_track_data
    # func and avoid parsing the rekordbox xml again or re-searching already
    # finished tracks
    if (os.path.exists(tracks_csv_filepath)):
        print("Continuing track year updating...")

        orig_track_data_list = parse_csv_to_tuple_list(tracks_csv_filepath)

        last_processed_track = get_last_processed_track(
            track_years_csv_filepath)

        cont_track_data_list = create_continuation_track_data_list(
            last_processed_track, orig_track_data_list)

        # optional: write our continuation track list to a new file
        # output_to_csv(cont_track_data_list, "tracks-cont")

        update_track_data_with_possible_year(
            cont_track_data_list, track_years_csv_filepath)

    else:
        # ensure user has exported a current version of the Rekordbox.xml
        print("The rekordbox.xml file must be current or data will be incorrect.")
        input("If the rekordbox.xml file is current, press Enter to continue...")

        rekordbox_collection_files = parse_rekordbox_xml(
            rekordbox_xml, search_folders)

        track_data_list = extract_track_data(rekordbox_collection_files)

        # write our track data list to file
        output_to_csv(track_data_list, "tracks")

        update_track_data_with_possible_year(
            track_data_list, track_years_csv_filepath)


# -----------  Fix Malformed Data  ----------- #

# data could have been malformed by bad csv writes where
# commas were a part of the track file path or artist entry.
# this finds and fixes it using the correct csv.writeline method
def fix_malformed_data():
    track_years_data_list = parse_csv_to_tuple_list(track_years_csv_filepath)

    for idx, item in enumerate(track_years_data_list):
        # get index of malformed data which is any tuple longer than 6
        if len(item) > 6:
            # this is the line we will replace in the track-years csv (data is broken on this line)
            broken_data = parse_csv_to_tuple_list(
                track_years_csv_filepath)[idx]
            print(broken_data)

            # this is the item that will be inserted -  coming from tracks.csv (data is still in tact)
            correct_data = parse_csv_to_tuple_list(
                tracks_csv_filepath)[idx]
            possible_year = search_for_release_year(
                correct_data[3], correct_data[2])

            correct_data = correct_data + (possible_year,)
            print(correct_data)

            track_years_data_list[idx] = correct_data

    output_to_csv(track_years_data_list, "track-years")


# -----------  Fix Missing Years  ----------- #

# chatGPT may have not retured a release year.  it this case
# the entered year is "0".  this re-queries those entries.
def fix_missing_years(track_years_csv_filepath):
    track_years_data_list = parse_csv_to_tuple_list(track_years_csv_filepath)

    for idx, item in enumerate(track_years_data_list):
        # get index of malformed data which is any item that has "0" as the 6th item
        if str(item[5]) == "0":
            possible_year = search_for_release_year(
                item[3], item[2])

            # convert item to list
            track_data = list(item)

            # replace "0" with possible year
            track_data[5] = possible_year

            # convert back to tuple
            corrected_item = track_data

            # replace the current item in the track_data_list with updated item
            track_years_data_list[idx] = corrected_item

    output_to_csv(track_years_data_list, "track-years")


# -----------  Write Results to ID3 Tag  ----------- #

def write_year_to_id3_tag(track_years_csv_filepath, starting_idx):
    track_data_tuple_list = parse_csv_to_tuple_list(track_years_csv_filepath)

    if starting_idx:
        track_data_tuple_list = track_data_tuple_list[starting_idx:]

    for idx, item in enumerate(track_data_tuple_list):
        if not item[4] == item[5]:
            save_data = input(
                f"Year for {item[3]} by {item[2]} is {item[4]}.  Overwrite with {item[5]} (y/n/q): ")

            if save_data == "y":
                # write to id3 tag
                print("fake writing to id3 tag")
                continue

            elif save_data == "n":
                continue

            elif save_data == "q":
                print(f"==> Continue next time with index {idx}")
                break

            else:
                print(
                    f"==> Improper input, exiting.  Continue next time with index {idx}")
                break


# -----------  Run App Funcs  ----------- #
# get_track_release_year()
# fix_malformed_data()
# fix_missing_years(track_years_csv_filepath)
write_year_to_id3_tag(track_years_csv_filepath, 0)
