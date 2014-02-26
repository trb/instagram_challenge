"""Unshreds a shredded image. In the documentation, "strip" refers to a
verticle line of pixels from top to bottom of the image. A shred is a
consecutive collection of strips that "belong together" (i.e. are found in the
same order in the source image).

This module attempts to identify various shreds in the image of various width
and orders them.
"""

from PIL import Image

import sys
import collections

_image = None
_pixels = None

_width = 0
_height = 0

_shreds = []


class ImageNotOpenedError(Exception):
    pass


class PixelOutsideImage(Exception):
    pass


class RangeError(Exception):
    pass


class Shred(object):
    """Represents one detected shred from the image and provides functions to
    interact with other shreds/access data:
    
    getPixels():
        Generator that provides a tuple consiting of (x, y, value), where
        value is whatever open_image() provided in _pixels
    
    getStrips():
        Returns a list of strips in this shred
        
    getWidth():
        Returns the shreds span in pixel
        
    getRightIndex():
        Returns the location in the image of the right-most strip
        (x-coordinate)

    getLeftIndex():
        Same as getRightIndex() but for the left-most strip
    
    matchLeftOf(other_shred):
        Takes another shred, and matches this shred to the left side of the
        other shred. Basically, it takes a few strips from this shreds right
        side, and a few strips from the other shreds left side and returns
        the accumulated difference between those shreds.
        
        The difference to the other shred is saved in _left_matches.
        
    matchRightOf(other_shred):
        Like matchLeftOf() but for the other side. Stores the difference in
        _right_matches.
        
    getBestMatchLeft():
        Returns the shred that this shred left-matched best to
        
    setBestMatchLeft(other_shred):
        Specify the best left-match for this shred. The best match is manually
        set when best left-match for this shred is not the best right-match
        for matched shred.
        
    getBestMatchesLeft():
        Returns a list of shreds sorted by left-match difference from low to
        high (best to worst)
        
    getNthBestMatchLeft(n):
        Returns the first, seconds, ..nth best left-match
        
    getBestMatchRight, getBestMatchesRight, getNthBestMatchRight:
        Do the same as their left-equivalent, but for the right side.
    """
    def __init__(self, from_, to, id_):
        self.id = id_
        self._range = (from_, to)
        
        self._right_matches = {}
        self._left_matches = {}
        
    def getPixels(self):
        for x in xrange(*self._range):
            strip = _get_strips(x)[0]
            
            for y, value in enumerate(strip):
                yield (x, y, value)
        
    def getStrips(self):
        strips = _get_strips(*self._range)
        
        return strips
    
    def getWidth(self):
        # +1 since the range is inclusive on both ends, 0-31 = width of 32
        return (self._range[1] - self._range[0])+1
    
    def getRightStrip(self):
        return _get_strips(self._range[1])[0]
    
    def getRightIndex(self):
        return self._range[1]
    
    def getLeftStrip(self):
        return _get_strips(self._range[0])[0]
    
    def getLeftIndex(self):
        return self._range[0]
    
    def matchLeftOf(self, other_shred):
        self_range = (self.getRightIndex() - 2,
                      self.getRightIndex()
                      )
        
        right_strips = _get_strips(*self_range)
        
        other_range = (other_shred.getLeftIndex(),
                       other_shred.getLeftIndex() + 2)
        
        left_strips = _get_strips(*other_range)
        
        difference = 0
        for right_strip, left_strip in zip(right_strips, left_strips):
            difference+= _difference_strips(right_strip, left_strip)
            
        self._left_matches[other_shred.id] = difference
        other_shred._right_matches[self.id] = difference
            
        return difference
    
    def matchRightOf(self, other_shred):
        right_strips = _get_strips(other_shred.getRightIndex()-5,
                                   other_shred.getRightIndex())
        left_strips = _get_strips(self.getLeftIndex(),
                                  self.getLeftIndex()+5)
        
        difference = 0
        for right_strip, left_strip in zip(right_strips, left_strips):
            difference+= _difference_strips(right_strip, left_strip)
            
        self._right_matches[other_shred.id] = difference
        other_shred._left_matches[self.id] = difference
            
        return difference
    
    def getBestMatchLeft(self):
        return self.getNthBestMatchLeft(0)
    
    def setBestMatchLeft(self, shred):
        self._left_matches[shred.id] = 1
    
    def getBestMatchesLeft(self):
        return sorted(self._left_matches, key=self._left_matches.get)
    
    def getNthBestMatchLeft(self, index):
        # orders from low to high, ie best match to worst match
        ordered_matches = sorted(self._left_matches,
                                 key=self._left_matches.get)
        
        return (ordered_matches[index],
                self._left_matches[ordered_matches[index]])
    
    def getBestMatchRight(self):
        return self.getNthBestMatchRight(0)
    
    def getBestMatchesRight(self):
        return sorted(self._right_matches, key=self._right_matches.get)
    
    def getNthBestMatchRight(self, index):
        # orders from low to high, ie best match to worst match
        ordered_matches = sorted(self._right_matches,
                                 key=self._right_matches.get)
        
        return (ordered_matches[index],
                self._right_matches[ordered_matches[index]])
        
        
class Shreds(object):
    """Keeps a collection of shreds that can be iterated. Allows to get/delete
    shreds specified by a shred id:
    
    add(shred):
        Adds shred to the collection
        
    get(shred_id):
        Returns a specific shred
        
    remove(shred_id):
        Removes a specific shred
    """
    def __init__(self):
        self.shreds = {}
        
    def add(self, shred):
        self.shreds[shred.id] = shred
        
    def __iter__(self):
        for shred in self.shreds.itervalues():
            yield shred
            
    def get(self, shred_id):
        return self.shreds[shred_id]
    
    def remove(self, shred_id):
        del self.shreds[shred_id]


def open_image(file_name):
    global _image
    global _pixels
    
    _image = Image.open(file_name)
    _pixels = _image.load()


def _check():
    if _image is None or _pixels is None:
        raise ImageNotOpenedError('Call open_image() first')
  
    
def _checkPixelBoundaries(x=None, y=None):
    _check()
    
    width, height = _image.size
    
    if x is not None:
        if x > width:
            raise PixelOutsideImage('x is larger than image width')
        if x < 0:
            raise PixelOutsideImage('x is smaller than 0')
    
    if y is not None:
        if y > height:
            raise PixelOutsideImage('y is larger than image height')
        if y < 0:
            raise PixelOutsideImage('y is maller than 0')


def _difference_points(point_a, point_b):
    """Only works for RGB values at the moment (and RGBA, but A is ignored).
    Returns the combined difference between the RGB values.
    """
    if len(point_a) != len(point_b):
        raise ValueError('both points must be of the same format')
    
    rd = abs(point_a[0] - point_b[0])
    gd = abs(point_a[1] - point_b[1])
    bd = abs(point_a[2] - point_b[2])
    
    return rd + gd + bd


def _difference_strips(strip_a, strip_b):
    """Returns the accumulated difference of points in strip_ab and strip_b
    """
    if len(strip_a) != len(strip_b):
        raise RangeError('strip_a and strip_b have to have the same length')

    sum_difference = 0
    for i in xrange(0, len(strip_a)):
        sum_difference+= _difference_points(strip_a[i], strip_b[i])
    
    return sum_difference / len(strip_a)


def _acc_difference_strips(strips):
    """Returns the average difference between strips for more than two strips
    """
    x = 0
    difference = 0
    while x + 1 < len(strips):
        difference+= _difference_strips(strips[x], strips[x+1])
        
        x+= 1
        
    return difference / x


def _get_strips(from_, to=None):
    """Returns a list of strips between from_ and to pixels in the image
    """
    height = _image.size[1]
    
    # Returns only one line
    if to is None:
        to = from_

    _checkPixelBoundaries(x=from_)
    _checkPixelBoundaries(x=to)
    
    if to < from_:
        raise RangeError('to is smaller than from')
    
    strips = []
    # to + 1 = to is inclusive
    for x in xrange(from_, to + 1):
        strip = []
        for y in xrange(0, height):
            strip.append(_pixels[x, y])
            
        strips.append(strip)
        
    return strips


def _scan_for_shreds():
    """Identifies shreds in image and returns a list of found shreds.
    
    The algorithm is simple, if two consecutive strips differ greatly, a new
    shreds was probably found.
    
    This produces false positives in high contrast high frequency areas. If the
    following couple of strips have a high average difference too, the match is
    ignored since it's probably in a high contrast high frequency area and
    therefore a false positive.
    
    It's implemented by taking a ratio of the following differences and the
    found difference. If the ratio is too high, the match is ignored.
    For the test image, 0.68 as a ratio cutoff works fine, but this might
    not work with other images.
    
    This method is not a good generalized method and leaves room for
    improvement, e.g. identifying horizontal lines (which a shred would break
    up), or analysing the frequency of a shred (should be different for
    different shreds).
    """
    # look-ahead of three, so don't check the last few pixels
    strips = _get_strips(0, _image.size[0]-3)

    shreds = Shreds()
    
    i = 0
    start = 0
    count = 1
    while i + 1 < len(strips):
        # 119 is a rough estimate, might not work depending on image structure
        difference = _difference_strips(strips[i], strips[i+1]) 
        if difference > 119:
            post_difference = _acc_difference_strips(_get_strips(i+1, i+3))
            
            if (float(post_difference)/difference) < 0.68:
                shreds.add(Shred(start, i, count))
        
                # next shred should start on i+1
                start = i+1
                count+= 1
        
        # has to be after if block, since if block needs original i value
        i+= 1
        
    # Add all remaining strips to the shred, 0-based dimensions therefore -1
    shreds.add(Shred(start, _image.size[0]-1, count))
    
    return shreds
    
    
def unshred():
    """Orders the shreds _scan_for_shreds() returns.
    
    It identifies the right-most shred by taking the ratio of the best right-of
    match and the best left-of match. For the righ-most shred, the left-of
    match will be a false positive and the difference quite high, while the
    right-of match will be a good match. Therefore, if the ratio of right-of to
    left-of will be small. The smallest such value will identify the right-most
    shred.
    
    The right-most shred is added to the ordered-deque and removed from the
    shreds-deque and the other shreds are assembled like this:
    
    Take first shred from shreds-deque. Check if the head of the sorted-deque
    is the best left-of match of the shred. If not, add shred to the back of
    the shreds-deque. If yes, add shred to the front of the sorted-deque. This
    is continued until the shreds-deque is done.
    """
     
    shreds = _scan_for_shreds()
    
    # Match shreds to each other
    for shred in shreds:
        for other_shred in shreds:
            if other_shred.id == shred.id:
                continue
            
            shred.matchLeftOf(other_shred)

    # Filter bad matches
    for shred in shreds:
        best_left = shred.getBestMatchLeft()
        if shred.id != shreds.get(best_left[0]).getBestMatchRight()[0]:
            for other_shred_id in shred.getBestMatchesLeft():
                other_shred = shreds.get(other_shred_id)
                
                if other_shred.getBestMatchRight()[0] == shred.id:
                    shred.setBestMatchLeft(other_shred)
                    
    """Lowest ratio is one where the left match is good but right match is
    bad. This will be the right-most shred, since the right-side match will be
    a mismatch and have a high error score, while the left side will have a
    good and low error score
    """
    
    lowest_ratio = sys.maxint
    rightmost_shred = None 
    for shred in shreds:
        ml = shred.getBestMatchLeft()
        mr = shred.getBestMatchRight()
        
        ratio = mr[1] / float(ml[1])
        
        # Ignore high ratios of best match overwrites
        if ratio < lowest_ratio:
            lowest_ratio = ratio
            rightmost_shred = shred

    shreds.remove(rightmost_shred.id)
    
    new_shreds = []
    new_shreds.append(rightmost_shred)
    
    shreds_list = collections.deque()
    for shred in shreds:
        shreds_list.append(shred)
    
    new_shreds = collections.deque()
    new_shreds.append(rightmost_shred)
    
    while len(shreds_list) > 0:
        shred = shreds_list.popleft()
        
        left_of = shred.getBestMatchLeft()[0]
        
        if new_shreds[0].id == left_of:
            new_shreds.appendleft(shred)
        else:
            shreds_list.append(shred)
    
    return new_shreds
                            

def assemble(shreds, file_name):
    image = Image.new('RGBA', _image.size)
    pixels = image.load()
    
    x, y = 0, 0
    for shred in shreds:
        strips = shred.getStrips()
        
        for strip in strips:
            for y, value in enumerate(strip):
                pixels[x, y] = value
                
            x+= 1
            
    image.save(file_name)


if __name__ == "__main__":
    try:
        input_file = sys.argv[1]
    except:
        input_file = 'TokyoPanoramaShredded.png'
        
    try:
        output_file = sys.argv[2]
    except:
        output_file = 'unshredded.png'
    
    open_image(input_file)
    
    shreds = unshred()
    
    assemble(shreds, output_file)
    
    print 'saved to', output_file
