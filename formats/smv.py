'''
Created on Nov 25, 2010

@author: michel
'''
import ctypes
import re
import os
import numpy
from PIL import Image
from ..import utils
from . import DataSet

DECODER_DICT = {
    "unsigned_short": (ctypes.c_uint16, 'F;16','F;16B'),
    "unsigned_int": (ctypes.c_uint, 'F;32','F;32B'),
    "signed_short": (ctypes.c_int16, 'F;16S','F;16BS'),
    "signed_int": (ctypes.c_int, 'F;32S','F;32BS'),
}

def read_smv(filename, with_image=True):
    info = {}
    myfile = open(filename, 'r')
    raw = myfile.read(512)
    raw_entries = raw.split('\n')
    tmp_info = {}
    epat = re.compile('^(?P<key>[\w]+)=(?P<value>.+);')
    for line in raw_entries:
        m = epat.match(line)
        if m:
            tmp_info[m.group('key').lower()] = m.group('value').strip()
    # Read remaining header if any
    _header_size = int(tmp_info['header_bytes'])
    if _header_size > 512:
        raw = myfile.read(_header_size - 512)
        raw_entries = raw.split('\n')
        for line in raw_entries:
            m = epat.match(line)
            if m:
                tmp_info[m.group('key').lower()] = m.group('value').strip()
    myfile.close()
    _type = tmp_info.get('type', "unsigned_short")
    _el_type = DECODER_DICT[_type][0]

    # decoder suffix for endianess
    if tmp_info.get('byte_order') == 'big_endian':
        _raw_decoder = DECODER_DICT[_type][2]
    else:
        _raw_decoder = DECODER_DICT[_type][1]
    info['delta_angle'] = float(tmp_info['osc_range'])
    info['distance'] = float(tmp_info['distance'])
    info['wavelength'] = float(tmp_info['wavelength'])
    info['exposure_time'] = float(tmp_info['time'])
    info['pixel_size'] = float(tmp_info['pixel_size'])
    orgx = float(tmp_info['beam_center_x']) / info['pixel_size']
    orgy = float(tmp_info['beam_center_x']) / info['pixel_size']
    info['detector_size'] = (int(tmp_info['size1']), int(tmp_info['size2']))
    info['beam_center'] = (orgx, info['detector_size'][1] - orgy)

    # use image center if detector origin is (0,0)
    if sum(info['beam_center']) < 0.1:
        info['beam_center'] = (info['detector_size'][0] / 2.0, info['detector_size'][1] / 2.0)
    info['start_angle'] = float(tmp_info['osc_start'])
    if tmp_info.get('twotheta') is not None:
        info['two_theta'] = float(tmp_info['twotheta'])
    else:
        info['two_theta'] = 0.0

    if info['detector_size'][0] == 2304:
        info['detector_type'] = 'q4'
    elif info['detector_size'][0] == 1152:
        info['detector_type'] = 'q4-2x'
    elif info['detector_size'][0] == 4096:
        info['detector_type'] = 'q210'
    elif info['detector_size'][0] == 2048:
        info['detector_type'] = 'q210-2x'
    elif info['detector_size'][0] == 6144:
        info['detector_type'] = 'q315'
    elif info['detector_size'][0] == 3072:
        info['detector_type'] = 'q315-2x'
    info['filename'] = filename
    info['saturated_value'] = 2 ** (8 * ctypes.sizeof(_el_type)) - 1

    if with_image:
        num_el = info['detector_size'][0] * info['detector_size'][1]
        el_size = ctypes.sizeof(_el_type)
        data_size = num_el * el_size
        with open(filename, 'rb') as myfile:
            myfile.read(_header_size)
            data = myfile.read(data_size)
        raw_image = Image.frombytes('F', info['detector_size'], data, 'raw', _raw_decoder)
        raw_data = numpy.fromstring(data, dtype=_el_type).reshape(*info['detector_size'])
    else:
        raw_data = None
        raw_image = None

    return info, raw_data, raw_image


class SMVDataSet(DataSet):
    def __init__(self, filename, header_only=False):
        super(SMVDataSet, self).__init__()
        self.filename = filename
        self.header = {}
        self.data = None
        self.image = None
        p0 = re.compile('^(?P<root_name>.+)_\d+\.cbf$')
        m0 = p0.match(self.filename)
        if m0:
            params = m0.groupdict()
            self.root_name = params['root_name']
        else:
            self.root_name = filename
        self.name = os.path.basename(self.root_name)

        self.current_frame = 1
        self.raw_header, self.raw_data, self.raw_image = read_smv(filename)
        self.read_header()
        if not header_only:
            self.read_image()

    def read_header(self):
        self.header = {}
        self.header.update(self.raw_header)
        self.header.update({
            'name': self.name,
            'format': 'SMV',
            'dataset': utils.file_sequences(self.filename),
        })
        if self.header['dataset']:
            self.current_frame = self.header['dataset']['current']


    def read_image(self):
        self.data = self.raw_data.T
        self.image = self.raw_image.convert('I')
        self.header['average_intensity'] = max(0.0, self.data.mean())
        self.header['min_intensity'], self.header['max_intensity'] = self.data.min(), self.data.max()
        self.header['gamma'] = utils.calc_gamma(self.header['average_intensity'])
        self.header['overloads'] = len(numpy.where(self.data >= self.header['saturated_value'])[0])

    def check_disk_frames(self):
        self.header['dataset'] = utils.file_sequences(self.filename)

    def get_frame(self, index=1):
        """
        Load a specific frame
        :param index: frame index
        :return:
        """
        if self.header['dataset']:
            tmpl = self.header['dataset']['name'].format(index)
            filename = tmpl.format(index)
            if os.path.exists(filename):
                self.raw_header, self.raw_data, self.raw_image = read_smv(filename, True)
                self.read_header()
                self.read_image()
                self.current_frame = index
                return True
        return False

    def next_frame(self):
        """Load the next frame in the dataset"""
        next_frame = self.current_frame + 1
        return self.get_frame(next_frame)

    def prev_frame(self):
        """Load the previous frame in the dataset"""
        next_frame = self.current_frame - 1
        return self.get_frame(next_frame)



__all__ = ['SMVDataSet']
