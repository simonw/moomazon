from google.appengine.ext import webapp
from google.appengine.api.urlfetch import fetch
import logging, urllib
from xml.dom import minidom

from django.utils.text import wrap

AWS_ACCESS_KEY = 'AWS-ACCESS-KEY-GOES-HERE'
MOO_API_KEY = 'MOO-KEY-GOES-HERE'

def amazon_search_url(q):
    return 'http://ecs.amazonaws.com/onca/xml?' + urllib.urlencode({
        'Service': 'AWSECommerceService',
        'AWSAccessKeyId': AWS_ACCESS_KEY,
        'Operation': 'ItemSearch',
        'SearchIndex': 'Books',
        'ResponseGroup': 'ItemAttributes,Images',
        'Version': '2008-08-19',
        'Keywords': q,
    })

def get_node_value(context, tag):
    try:
        return context.getElementsByTagName(tag)[0].firstChild.nodeValue
    except:
        return ''

def amazon_search(q):
    """
    Returns a dictionary that looks like this:
    
    {
        'title': '...',
        'authors': ['...'],
        'asin': '...',
        'isbn': '...',
        'publisher': '...',
        'publication_date': '...',
    }
    """
    url = amazon_search_url(q)
    dom = minidom.parseString(fetch(url).content)
    items = dom.getElementsByTagName('Item')
    return [item_details(item) for item in items if item_details(item)]

def amazon_details(asin):
    url = 'http://ecs.amazonaws.com/onca/xml?' + urllib.urlencode({
        'Service': 'AWSECommerceService',
        'AWSAccessKeyId': AWS_ACCESS_KEY,
        'Operation': 'ItemLookup',
        'ResponseGroup': 'ItemAttributes,Images',
        'Version': '2008-08-19',
        'ItemId': asin,
    })
    dom = minidom.parseString(fetch(url).content)
    return item_details(dom.getElementsByTagName('Item')[0])

def item_details(item):
    attributes = item.getElementsByTagName('ItemAttributes')[0]
    try:
        images = dict([
            (n.nodeName.replace('Image', '').lower(), {
                'url': get_node_value(n, 'URL'),
                'width': int(get_node_value(n, 'Width')),
                'height': int(get_node_value(n, 'Height')),
            })
            for n in item.getElementsByTagName('ImageSet')[0].childNodes
        ])
    except IndexError:
        return {} # Skip the ones with no images
    return {
        'asin': get_node_value(item, 'ASIN'),
        'title': get_node_value(attributes, 'Title'),
        'publisher': get_node_value(attributes, 'Publisher'),
        'publication_date': get_node_value(attributes, 'PublicationDate'),
        'isbn': get_node_value(attributes, 'ISBN'),
        'authors': [
            n.firstChild.nodeValue 
            for n in attributes.getElementsByTagName('Author')
        ],
        'images': images,
    }

def make_lines_for_book(book):
    title = wrap(book['title'], 37)
    lines = []
    for line in title.split('\n'):
        lines.append([
            ('string', line),
            ('bold', 'true'),
            ('align', 'left'),
            ('font', 'modern'),
        ])
    authors = book['authors']
    if len(authors) == 1:
        by = 'By %s' % authors[0]
    elif len(authors) == 2:
        by = 'By %s and %s' % (authors[0], authors[1])
    else:
        try:
            by = 'By %s and %s' % (', '.join(authors[:-1]), authors[-1])
        except IndexError:
            by = None
    if by:
        by = wrap(by, 37)
        for line in by.split('\n'):
            lines.append([
                ('string', line),
            ])
    lines.append([
        ('string', 'ISBN: %s' % book['isbn']),
    ])
    return lines

def make_xml_for_book(book):
    # We need to wordwrap everything to 37 lines
    return render('moo.xml', {
        'lines': make_lines_for_book(book),
        'book': book,
        'api_key': MOO_API_KEY,
    })

class Moomazon(webapp.RequestHandler):
    def get(self):
        asin = self.request.get('asin', default_value = '')
        q = self.request.get('q', default_value = '')
        if asin:
            return self.do_asin(asin)
        if q:
            return self.do_search(q)
        
        self.response.out.write(render('index.html'))
    
    def do_search(self, q):
        results = amazon_search(q)
        for result in results:
            result['xml'] = make_xml_for_book(result)
            result['lines'] = [{
                'bold': len([l for l in lines if l[0] == 'bold']),
                'string': [l[1] for l in lines if l[0] == 'string'][0],
            } for lines in make_lines_for_book(result)]
        self.response.out.write(render('results.html', {
            'results': results,
            'q': q,
        }))
    
    def do_asin(self, asin):
        details = amazon_details(asin)
        self.response.out.write(make_xml_for_book(details))
        
def main():
    logging.getLogger().setLevel(logging.DEBUG)
    from wsgiref.handlers import CGIHandler
    application = webapp.WSGIApplication([
        #('/', makeStatic('index.html')),
        #('/time.json', JsonTime),
        ('/.*$', Moomazon),
    ], debug=True)
    CGIHandler().run(application)

import os
template_dir = os.path.join(os.path.dirname(__file__), 'templates')
from google.appengine.ext.webapp import template
def render(template_name, context={}):
    path = os.path.join(template_dir, template_name)
    return template.render(path, context)

if __name__ == "__main__":
    main()
