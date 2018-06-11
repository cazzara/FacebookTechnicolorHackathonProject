#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Jun  9 17:53:41 2018

@author: azzarac

This script will perform a keyword search on Pinterest and extract the image urls and download them
"""

import time
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
import bs4
import requests
from google.cloud import vision
from google.cloud.vision import types
import json
import re
import os
from operator import itemgetter
from PIL import Image, ImageDraw, ImageFont


IMG_PATH = '/Users/azzarac/PythonProjects/PinterestScrapper/imgs/'
PIN_INFO_URL = 'http://widgets.pinterest.com/v3/pidgets/pins/info/?pin_ids={}'
PINTEREST_SEARCH_URL_BEACH = 'https://www.pinterest.com/js3416/beach-quotes/'
PINTEREST_SEARCH_URL_DAD = 'https://www.pinterest.com/js3416/fathers-day/'
BACKGROUND_IMAGE_PATH_BEACH = '/Users/azzarac/PythonProjects/PinterestScrapper/bkgnd-imgs/starfish_small.png'
BACKGROUND_IMAGE_PATH_DAD = '/Users/azzarac/PythonProjects/PinterestScrapper/bkgnd-imgs/transparent.png'
FONT_BASE_DIR= '/Users/azzarac/PythonProjects/PinterestScrapper/Fonts/'
#FONTS = os.listdir(FONT_BASE_DIR)
FONT_BEACH = 'LittleBestseller-Regular.ttf'
FONT_DAD = 'Montserrat-Bold.ttf'
IMAGE_SAVE_PATH = '/Users/azzarac/PythonProjects/PinterestScrapper/designs/'
TOP_PINS = 50 # return the top 50 saved pins from the search

FONT_SIZE = 150 # font size for text on image
client = vision.ImageAnnotatorClient()
image = types.Image()

def analyzeImage(client, image, url):
    image.source.image_uri = url
    response = client.text_detection(image=image)
    texts = response.text_annotations
    ret_text = ""
    for text in texts:
        ret_text = text.description
        break
    return ret_text

def extractUrl(img_tag):
    # Extract the url for the highest resolution image
    contents = img_tag.contents[0]
    img_urls = contents['srcset']
    return img_urls.split(',')[-1].strip().rstrip(' 3x')

def linkIsPin(l):
    try:
        l.attrs['data-pwt']
    except KeyError:
        return False
    else:
        return True

def filterLinks(links):
    imgs =[]
    for l in links:
        if linkIsPin(l):
            imgs.append(l)
    return imgs
    
def extractFilename(url):
    return url.split('/')[-1]

def writeImageToFile(url, file_name):
    img = requests.get(url)
    with open(IMG_PATH + file_name, 'wb') as f:
        for chunk in img:
            f.write(chunk)
            
def pageDown(n, element):
    while n:
        element.send_keys(Keys.PAGE_DOWN)
        time.sleep(0.2)
        n -= 1

def getPinIDs(html):
    pin_pattern = re.compile(r"pin/\d+")    
    pins = pin_pattern.findall(html)
    ids = []
    for pin in pins:
        ids.append(pin.split('/')[1])
    return ids

def combinePinIdsAndLinks(pin_ids, imgs):
    return zip(pin_ids, imgs)

def getSaves(pin_id):
    r = requests.get(PIN_INFO_URL.format(pin_id))
    info = json.loads(r.text)
    return info['data'][0]['aggregated_pin_data']['aggregated_stats']['saves']

def text_wrap(text, font, max_width):
    text = text.split('\n')
    s = ''
    for t in text:
        s += t + ' '
    s = s.strip()
    text = s
    lines = []
    # If the width of the text is smaller than image width
    # we don't need to split it, just add it to the lines array
    # and return
    if font.getsize(text)[0] <= max_width:
        lines.append(text) 
    else:
        # split the line by spaces to get words
        words = text.split(' ')  
        i = 0
        # append every word to a line while its width is shorter than image width
        while i < len(words):
            line = ''         
            while i < len(words) and font.getsize(line + words[i])[0] <= max_width:                
                line = line + words[i] + " "
                i += 1
            if not line:
                line = words[i]
                i += 1
            # when the line gets longer than the max width do not append the word, 
            # add the line to the lines array
            lines.append(line)    
    return lines


def generateImage(text, file_name, BACKGROUND_IMAGE_PATH, font_name):
    if len(text) > 150:
        print("Too Long!")
        return
    if len(text) < 10:
        print("Too Short!")
        return
    
    bkgrnd_image = Image.open(BACKGROUND_IMAGE_PATH)

    image_width = bkgrnd_image.size[0]
    draw = ImageDraw.Draw(bkgrnd_image)
    font_dir = font_name.rstrip('.ttf') + '/'
    font = ImageFont.truetype(FONT_BASE_DIR + font_name, FONT_SIZE)
    text_lines = text_wrap(text, font, image_width)
    print(text_lines)
    x = 10
    y = 20
    line_height = font.getsize('hg')[1]
    for text in text_lines:
        if font_name == "LittleBestseller-Regular.ttf":
            text = text.lower()
        draw.text((x, y), text, font=font, fill=(0,0,0))
        y += line_height
    if not os.path.exists(IMAGE_SAVE_PATH + font_dir):
        os.mkdir(IMAGE_SAVE_PATH + font_dir)
    bkgrnd_image.save(IMAGE_SAVE_PATH + font_dir + file_name + ".png")
        
def getSourceHTML(URL):
   # Launch a Chrome instance and open a Pinterest page containing the keyword search
   print("Launching Chrome and Navigating to {}!".format(URL))
   browser = webdriver.Chrome('/usr/local/bin/chromedriver') # had to manually specify the location of the 'chromedriver' binary
   browser.get(URL)
   time.sleep(1.5)  
   # Take focus of the body element of the main page
   elem = browser.find_element_by_tag_name("body")
   # In order to circumvent the "infinite scroll" loading page mechanism on Pinterest
   no_of_pagedowns = 10
   # Send the page down key to load more pins!
   pageDown(no_of_pagedowns, elem)
   source = browser.page_source
   # Close the browser, we done
   browser.close()
   return source

def getPinMetaData(imgs_and_ids):
    urls_file_names_saves = []
    print("Collecting Pin Metadata")
    for pin_id, img in imgs_and_ids:
        saves = getSaves(pin_id)
        img_url = extractUrl(img)
        file_name = extractFilename(img_url)
        urls_file_names_saves.append((img_url, file_name, saves))
    urls_file_names_saves.sort(key=itemgetter(2), reverse=True)
    return urls_file_names_saves

def scrapeHTML(soup):
    # Find all the image links
    links = soup.findAll("a") # list containing all links/images
    pin_ids = getPinIDs(source)
    imgs = filterLinks(links)
    imgs_and_ids = combinePinIdsAndLinks(pin_ids, imgs)
    print("Got {} images to analyze, looking at the top {} saved images".format(len(imgs), TOP_PINS))
    return imgs_and_ids


####################### BEACH QUOTES SCRAPE #############################
source = getSourceHTML(PINTEREST_SEARCH_URL_BEACH)
# Soupify the source HTML from the web browser
bs = bs4.BeautifulSoup(source, "html.parser")
 
imgs_and_ids = scrapeHTML(bs)

urls_file_names_saves = getPinMetaData(imgs_and_ids)

print("Performing OCR Analysis")
for i in range(TOP_PINS):
    img_url, file_name, saves  = urls_file_names_saves[i]
    print("Analyzing {} has {} saves".format(file_name, saves))
    img_text = analyzeImage(client, image, img_url)
    print(img_text)
    img_file_name = file_name.rstrip(".jpg")
    generateImage(img_text, img_file_name, BACKGROUND_IMAGE_PATH_BEACH, FONT_BEACH)
    
####################### DAD DAY QUOTES SCRAPE #############################
source = getSourceHTML(PINTEREST_SEARCH_URL_DAD)
# Soupify the source HTML from the web browser
bs = bs4.BeautifulSoup(source, "html.parser")
 
imgs_and_ids = scrapeHTML(bs)

urls_file_names_saves = getPinMetaData(imgs_and_ids)

print("Performing OCR Analysis")
for i in range(TOP_PINS):
    img_url, file_name, saves  = urls_file_names_saves[i]
    print("Analyzing {} has {} saves".format(file_name, saves))
    img_text = analyzeImage(client, image, img_url)
    print(img_text)
    img_file_name = file_name.rstrip(".jpg")
    generateImage(img_text, img_file_name, BACKGROUND_IMAGE_PATH_DAD, FONT_DAD)    
    
    