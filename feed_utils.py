import requests
import xml.etree.ElementTree as ElTree
import re


def get_guid_values_from_url(xml_url):
    # Fetch the XML content from the URL
    response = requests.get(xml_url)
    if response.status_code != 200:
        print("Failed to fetch XML from URL:", xml_url)
        return []

    # Parse the XML content
    root = ElTree.fromstring(response.content)

    # Array to store GUID values
    guid_values = []

    # Find all <guid> elements and extract their values
    for guid_element in root.iter('guid'):
        guid_values.append(guid_element.text)

    return guid_values


def extract_guid_numbers(value):
    # Regular expression pattern to match the numbers at the end of the string
    pattern = r'.*-(\d+)(?:\.(\d+))?'

    # Match the pattern in the given value
    match = re.match(pattern, value)

    if match:
        # Extract the first and second numbers
        first_number = int(match.group(1))
        second_number = int(match.group(2)) if match.group(2) else -1
        return first_number, second_number
    else:
        return -1, -1

def fix_hyphenated_numbers(text):
    return re.sub(r'(\d+)-(\d+)', r'\1.\2', text)

def extract_guid_numbers_hyphens(value):
    return extract_guid_numbers(fix_hyphenated_numbers(value))
