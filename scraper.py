import requests
from bs4 import BeautifulSoup

def get_novel_text(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Depending on the structure of the site, you may need to find the specific element that holds the text.
    # This is typically a div or a p tag, and may have a specific class or id.
    text_div = soup.find('div', {'class': "entry-content wp-block-post-content has-global-padding is-layout-constrained"}) 
    print(text_div)
    return text_div.text

# Get the text for a specific chapter
chapter_text = get_novel_text('https://lorenovels.com/chapter-63-the-school-trip/')

print(chapter_text)
