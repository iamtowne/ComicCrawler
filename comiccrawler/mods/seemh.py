#! python3

"""this is seemh module for comiccrawler

Ex:
	http://tw.seemh.com/comic/10924/
	http://www.seemh.com/comic/10924/

"""

import re
from urllib.parse import urljoin

from node_vm2 import VM, eval

from ..core import Episode, grabhtml, CycleList

domain = ["tw.seemh.com", "www.seemh.com", "ikanman.com"]
name = "看漫畫"
config = {
	"nowebp": "False"
}

def get_title(html, url):
	return re.search(r'<h1>([^<]*)', html).group(1)

def get_list(html, cid):
	ep_re = r'href="(/comic/{}/\d+\.html)" title="([^"]+)"'.format(cid)
	arr = []
	try:
		comment_pos = html.index('class="comment-bar"')
	except ValueError:
		comment_pos = len(html)

	for match in re.finditer(ep_re, html):
		if match.start() >= comment_pos:
			break
		ep_url, title = match.groups()
		arr.append((title, ep_url))
	return arr


def get_episodes(html, url):
	cid = re.search(r"comic/(\d+)", url).group(1)
	episodes = get_list(html, cid)

	if not episodes:
		ep_html = grabhtml(urljoin(url, "/support/chapters.aspx?id=" + cid), referer=url)
		episodes = get_list(ep_html, cid)

	episodes = [Episode(v[0].strip(), urljoin(url, v[1])) for v in episodes]
	return episodes[::-1]
	
servers = None

def get_images(html, url):
	# build js context
	js = "var window = global;"
	
	configjs_url = re.search(
		r'src="(http://[^"]+?/config_\w+?\.js)"',
		html
	).group(1)
	configjs = grabhtml(configjs_url, referer=url)
	js += re.search(
		r'^(var CryptoJS|window\["\\x65\\x76\\x61\\x6c"\]).+',
		configjs,
		re.MULTILINE
	).group()

	js += re.search(
		r'<script type="text/javascript">((eval|window\["\\x65\\x76\\x61\\x6c"\]).+?)</script',
		html
	).group(1)
	
	with VM(js) as vm:
		files, path = vm.run("[cInfo.files, cInfo.path]")
	
	# find server
	# "http://c.3qfm.com/scripts/core_5C348B32A78647FF4208EACA42FC5F84.js"
	# getpath()
	corejs_url = re.search(
		r'src="(http://[^"]+?/core_\w+?\.js)"',
		html
	).group(1)
	corejs = grabhtml(corejs_url, referer=url)
	
	# cache server list
	servs = re.search(r"var servs=(.+?),pfuncs=", corejs).group(1)
	servs = eval(servs)
	servs = [host["h"] for category in servs for host in category["hosts"]]
	
	global servers
	servers = CycleList(servs)

	host = servers.get()
	
	utils = re.search(r"SMH\.(utils=.+?),SMH\.imgData=", corejs).group(1)
	
	js = utils + """;
	function getFiles(path, files, host) {
		// lets try if it will be faster in javascript
		return files.map(function(file){
			return utils.getPath(host, path + file);
		});
	}
	"""
	with VM(js) as vm:
		images = vm.call("getFiles", path, files, host)
	
	if config.getboolean("nowebp"):
		images = map(lambda i: i[:-5] if i.endswith(".webp") else i, images)
	
	return images
	
def errorhandler(err, crawler):
	"""Change host"""
	if crawler.image and crawler.image.url:
		servers.next()
		host = servers.get()
		crawler.image.url = re.sub(
			r"://.+?\.",
			"://{host}.".format(host=host),
			crawler.image.url
		)
