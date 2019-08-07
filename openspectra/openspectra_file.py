#  Developed by Joseph M. Conti and Joseph W. Boardman on 1/21/19 6:29 PM.
#  Last modified 1/21/19 6:29 PM
#  Copyright (c) 2019. All rights reserved.
import copy
import logging
from abc import ABC, abstractmethod
from math import cos, sin
from pathlib import Path
import re
from typing import List, Union, Tuple, Dict
import numpy as np

from openspectra.utils import LogHelper, Logger


class LinearImageStretch(ABC):

    @staticmethod
    def create_default_stretch(parameters:str):
        result:LinearImageStretch = None
        if parameters is not None:
            if not re.match(".*linear$", parameters):
                raise OpenSpectraHeaderError("Only 'linear' 'default stretch' is supported, got: {0}", parameters)
            else:
                parts = re.split("\s+", parameters)
                if re.match("[0-9]*[\.][0-9]*%", parts[0]):
                    result = PercentageStretch(float(re.split("%", parts[0])[0]))
                elif len(parts) == 3:
                    result = ValueStretch(float(parts[0]), float(parts[1]))
                else:
                    raise OpenSpectraHeaderError("'default stretch' value is malformed, value was: {0}", parameters)

        return result

    @abstractmethod
    def percentage(self) -> Union[int, float]:
        raise NotImplementedError("Method not implemented on this class")

    @abstractmethod
    def low(self) -> Union[int, float]:
        raise NotImplementedError("Method not implemented on this class")

    @abstractmethod
    def high(self) -> Union[int, float]:
        raise NotImplementedError("Method not implemented on this class")


class PercentageStretch(LinearImageStretch):

    def __init__(self, percentage:Union[int, float]):
        self.__stretch = percentage

    def percentage(self) -> Union[int, float]:
        return self.__stretch

    def low(self) -> Union[int, float]:
        raise NotImplementedError("Method not implemented on this sub-class")

    def high(self) -> Union[int, float]:
        raise NotImplementedError("Method not implemented on this sub-class")


class ValueStretch(LinearImageStretch):

    def __init__(self, low:Union[int, float], high:Union[int, float]):
        self.__low = low
        self.__high = high

    def percentage(self) -> Union[int, float]:
        raise NotImplementedError("Method not implemented on this sub-class")

    def low(self) -> Union[int, float]:
        return self.__low

    def high(self) -> Union[int, float]:
        return self.__high


class OpenSpectraHeader:
    """A class that reads, validates and makes open spectra header file details available"""

    __LOG:Logger = LogHelper.logger("OpenSpectraHeader")

    _BAND_NAMES = "band names"
    _BANDS = "bands"
    __DATA_TYPE = "data type"
    __HEADER_OFFSET = "header offset"
    _INTERLEAVE = "interleave"
    _LINES = "lines"
    __REFLECTANCE_SCALE_FACTOR = "reflectance scale factor"
    _SAMPLES = "samples"
    _WAVELENGTHS = "wavelength"
    __WAVELENGTH_UNITS = "wavelength units"
    _MAP_INFO = "map info"
    __SENSOR_TYPE = "sensor type"
    __BYTE_ORDER = "byte order"
    __FILE_TYPE = "file type"
    __DESCRIPTION = "description"
    __DATA_IGNORE_VALUE = "data ignore value"
    __DEFAULT_STRETCH = "default stretch"
    _BAD_BAND_LIST = "bbl"

    __DATA_TYPE_DIC = {'1': np.uint8,
                       '2': np.int16,
                       '3': np.int32,
                       '4': np.float32,
                       '5': np.float64,
                       '6': np.complex64,
                       '9': np.complex128,
                       '12': np.uint16,
                       '13': np.uint32,
                       '14': np.int64,
                       '15': np.uint64}

    BIL_INTERLEAVE:str = "bil"
    BSQ_INTERLEAVE:str = "bsq"
    BIP_INTERLEAVE:str = "bip"

    class MapInfo:
        """"A simple class for holding map info from a header file"""

        __LOG: Logger = LogHelper.logger("OpenSpectraHeader.MapInfo")

        def __init__(self, map_info_list:List[str]=None, map_info=None):
            if map_info_list is not None:
                self.__init_from_list(map_info_list)
            elif map_info is not None:
                self.__init_from_map_info(map_info)
            else:
                raise ValueError("One of map_info_list or map_info must be passed")

        def __init_from_list(self, map_info_list:List[str]):
            # Example [UTM, 1.000, 1.000, 620006.407, 2376995.930, 7.8000000000e+000, 7.8000000000e+000, 4,
            # North, WGS-84, units=Meters, rotation=29.00000000]
            list_size = len(map_info_list)
            if list_size < 7:
                raise OpenSpectraHeaderError(
                    "Found map info but expected it to have at lease 7 elements, only found {0}".format(len(map_info_list)))

            # grab the minimal data
            self.__projection_name:str = map_info_list[0]
            self.__x_reference_pixel:float = float(map_info_list[1])
            self.__y_reference_pixel:float = float(map_info_list[2])
            self.__x_zero_coordinate:float = float(map_info_list[3])
            self.__y_zero_coordinate:float = float(map_info_list[4])
            self.__x_pixel_size:float = float(map_info_list[5])
            self.__y_pixel_size:float = float(map_info_list[6])

            self.__projection_zone:int = None
            self.__projection_area:str = None
            self.__datum:str = None
            self.__units:str = None
            self.__rotation:float = None

            index = 7
            if self.__projection_name == "UTM":
                if list_size < 9:
                    raise OpenSpectraHeaderError("Map info projection was UTM but zone and area parameters are missing");

                self.__projection_zone = int(map_info_list[index])
                index += 1
                self.__projection_area = map_info_list[index].strip()
                index += 1

            if list_size > index + 1:
                self.__datum = map_info_list[index].strip()
                index += 1

            for index in range(index, list_size):
                pair = re.split("=", map_info_list[index])
                if len(pair) == 2:
                    name:str = pair[0].strip()
                    value:str = pair[1].strip()
                    if name == "units":
                        self.__units:str = value
                    elif name == "rotation":
                        # TODO validate in range?
                        self.__rotation:float = float(value)
                    else:
                        OpenSpectraHeader.MapInfo.__LOG.warning(
                            "Ignoring unexpected map info item with name: {0}, value: {1}".format(name, value))
                else:
                    OpenSpectraHeader.MapInfo.__LOG.warning(
                        "Could not split map info item: {0}".format(map_info_list[index]))

        def __init_from_map_info(self, map_info):
            self.__projection_name = map_info.projection_name()
            self.__x_reference_pixel = map_info.x_reference_pixel()
            self.__y_reference_pixel = map_info.y_reference_pixel()
            self.__x_zero_coordinate = map_info.x_zero_coordinate()
            self.__y_zero_coordinate = map_info.y_zero_coordinate()
            self.__x_pixel_size = map_info.x_pixel_size()
            self.__y_pixel_size = map_info.y_pixel_size()
            self.__projection_zone = map_info.projection_zone()
            self.__projection_area = map_info.projection_area()
            self.__datum = map_info.datum()
            self.__units = map_info.units()
            self.__rotation = map_info.rotation()

        def __str__(self) -> str:
            param_list = [
                self.__projection_name,
                "{:.03f}".format(self.__x_reference_pixel),
                "{:.03f}".format(self.__y_reference_pixel),
                "{:.03f}".format(self.__x_zero_coordinate),
                "{:.03f}".format(self.__y_zero_coordinate),
                OpenSpectraHeader.MapInfo.__format_pixel_size(self.__x_pixel_size),
                OpenSpectraHeader.MapInfo.__format_pixel_size(self.__y_pixel_size),
                "{:d}".format(self.__projection_zone),
                self.__projection_area,
                self.__datum,
                "units={}".format(self.__units)]

            if self.__rotation is not None:
                param_list.append("rotation={:.08f}".format(self.__rotation))

            return "{" + ", ".join(param_list) + "}"

        @staticmethod
        def __format_pixel_size(value:float) -> str:
            val_str = "{:.010e}".format(value)
            if "e+" in val_str:
                parts = val_str.split("e+")
                if len(parts[1]) < 3:
                    parts[1] = "0".join(parts[1])

                val_str = "e+".join(parts)
            elif "e-" in val_str:
                parts = val_str.split("e-")
                if len(parts[1]) < 3:
                    parts[1] = "0".join(parts[1])
                val_str = "e-".join(parts)

            return val_str

        # TODO verify correctness
        def calculate_coordinates(self, x_pixels:Union[int, float, np.ndarray],
                y_pixels:Union[int, float, np.ndarray]) ->\
                Tuple[Union[float, np.ndarray], Union[float, np.ndarray]]:

            x_coords = (x_pixels - (self.__x_reference_pixel - 1)) * self.__x_pixel_size
            y_coords = (y_pixels - (self.__y_reference_pixel - 1)) * self.__y_pixel_size

            x_coords_rot = x_coords
            y_coords_rot = y_coords
            if self.__rotation is not None:
                # TODO figure out if rotation specified is clockwise or counterclockwise
                # This implementation is for counterclockwise rotation
                x_coords_rot = x_coords * cos(self.__rotation) - y_coords * sin(self.__rotation)
                y_coords_rot = x_coords * sin(self.__rotation) + y_coords * cos(self.__rotation)

            x_coords = x_coords_rot + self.__x_zero_coordinate
            y_coords = self.__y_zero_coordinate - y_coords_rot

            return x_coords, y_coords

        def projection_name(self) -> str:
            return self.__projection_name

        def x_reference_pixel(self) -> float:
            return self.__x_reference_pixel

        def y_reference_pixel(self) -> float:
            return self.__y_reference_pixel

        def x_zero_coordinate(self) -> float:
            return self.__x_zero_coordinate

        def y_zero_coordinate(self) -> float:
            return self.__y_zero_coordinate

        def x_pixel_size(self) -> float:
            return self.__x_pixel_size

        def y_pixel_size(self) -> float:
            return self.__y_pixel_size

        def projection_zone(self) -> int:
            return self.__projection_zone

        def projection_area(self) -> str:
            return self.__projection_area

        def datum(self) -> str:
            return self.__datum

        def units(self) -> str:
            return self.__units

        def rotation(self) -> float:
            return self.__rotation

    def __init__(self, file_name:str):
        self.__path = Path(file_name)
        self.__props:Dict[str, Union[str, List[str]]] = dict()

        self.__interleave:str = None
        self.__samples:int = 0
        self.__lines:int = 0
        self.__band_count:int = 0
        self.__wavelengths:np.array = None
        self.__band_labels:List[Tuple[str, str]] = None
        self.__header_offset:int = 0
        # TODO use standard float instead?
        self.__reflectance_scale_factor:np.float64 = np.float64(0.0)
        self.__map_info:OpenSpectraHeader.MapInfo = None
        self.__description:str = None
        self.__data_ignore_value: Union[int, float] = None
        self.__default_stretch:LinearImageStretch = None
        self.__bad_band_list:List[bool] = None

    def _copy_props(self) -> Dict[str, Union[str, List[str]]]:

        OpenSpectraHeader.__LOG.debug("original props: ")
        for key, value in self.__props.items():
            OpenSpectraHeader.__LOG.debug("key: {0}, value: {1}", key, value)

        props_copy = copy.deepcopy(self.__props)

        OpenSpectraHeader.__LOG.debug("props copy: ")
        for key, value in props_copy.items():
            OpenSpectraHeader.__LOG.debug("key: {0}, value: {1}", key, value)

        return props_copy

    def _get_prop(self, key:str) -> Union[str, List[str]]:
        result = self.__props.get(key)
        if result is not None and isinstance(result, list):
            result = result[:]

        return result

    def _set_props(self, props:Dict[str, Union[str, List[str]]]):
        self.__props = props
        self.__validate()

    def _update_prop(self, key:str, value:Union[int, str, List[str], np.ndarray], validate:bool=True):
        new_value = None
        if isinstance(value, int) :
            new_value = str(value)
        elif isinstance(value, np.ndarray):
            array_list = list(value)
            new_value = [str(item) for item in array_list]
        else:
            new_value = value

        self.__props[key] = new_value
        if validate:
            self.__validate()

    def dump(self) -> str:
        return "Props:\n" + str(self.__props)

    def load(self):
        OpenSpectraHeader.__LOG.debug("File: {0} exists: {1}", self.__path.name, self.__path.exists())

        if self.__path.exists() and self.__path.is_file():
            OpenSpectraHeader.__LOG.info("Opening file {0} with mode {1}", self.__path.name, self.__path.stat().st_mode)

            with self.__path.open() as headerFile:
                for line in headerFile:
                    line = line.rstrip()
                    if re.search("=", line) is not None:
                        line_pair:List[str] = re.split("=", line, 1)
                        key = line_pair[0].strip()
                        value = line_pair[1].lstrip()

                        if re.search("{", value):
                            self.__read_bracket(key, value, headerFile)
                        else:
                            self.__props[key] = value

            # now verify what we read makes sense and do some conversion to data type we want
            self.__validate()

        else:
            raise OpenSpectraHeaderError("File {0} not found".format(self.__path.name))

    def bad_band_list(self) -> List[bool]:
        """Return the bad band list that can be used to mask a numpy array
        In the header '1' means the band is good and '0' means it's bad.  But for an array
        mask True means the value is masked.  So in the list returned here '1' from
        the list in the header is converted to False and '0' to True"""
        return self.__bad_band_list

    def band_label(self, band:int) -> Tuple[str, str]:
        """Returns a tuple with the band name and wavelength"""
        return self.__band_labels[band]

    def band_labels(self) -> List[Tuple[str, str]]:
        """Returns a list of tuples, each tuple is the band name and wavelength """
        return self.__band_labels

    def band_name(self, band:int) -> str:
        """Returns the band name for the given band index"""
        return self.__props.get(OpenSpectraHeader._BAND_NAMES)[band]

    def band_names(self) -> List[str]:
        """Returns a list of strings of the band names"""
        return self.__props.get(OpenSpectraHeader._BAND_NAMES)

    def data_ignore_value(self) -> Union[int, float]:
        return self.__data_ignore_value

    def data_type(self):
        data_type = self.__props.get(OpenSpectraHeader.__DATA_TYPE)
        return self.__DATA_TYPE_DIC.get(data_type)

    def default_stretch(self) -> LinearImageStretch:
        return self.__default_stretch

    def description(self) -> str:
        return self.__description

    def samples(self) -> int:
        return self.__samples

    def lines(self) -> int:
        return self.__lines

    def band_count(self) -> int:
        return self.__band_count

    def file_type(self) -> str:
        return self.__props.get(OpenSpectraHeader.__FILE_TYPE)

    def wavelengths(self) -> np.array:
        return self.__wavelengths

    def wavelength_units(self) -> str:
        return self.__props.get(OpenSpectraHeader.__WAVELENGTH_UNITS)

    def interleave(self) -> str:
        return self.__interleave

    def header_offset(self) -> int:
        return self.__header_offset

    def sensor_type(self) -> str:
        return self.__props.get(OpenSpectraHeader.__SENSOR_TYPE)

    # TODO return standard float instead?
    def reflectance_scale_factor(self) -> np.float64:
        return self.__reflectance_scale_factor

    def map_info(self) -> MapInfo:
        return self.__map_info

    def __read_bracket(self, key, value, header_file):
        done = False
        line = value.strip("{").strip()
        list_value = list()

        # check for closing } on same line
        if re.search("}", line):
            line = line.strip("}").strip()
            done = True

        # if there are any entries on the first line handle them
        if line:
            elements = line.split(",")
            if len(elements) > 0:
                list_value = elements

        if not done:
            section = ""
            for line in header_file:
                section += line.rstrip()
                if re.search("}", line):
                    section = section.rstrip("}").rstrip()
                    break

            list_value += section.split(",")

        list_value = [str.strip(item) for item in list_value]
        self.__props[key] = list_value

    def __validate(self):
        interleave:str = self.__props.get(OpenSpectraHeader._INTERLEAVE).lower()
        if interleave == OpenSpectraHeader.BIP_INTERLEAVE:
            self.__interleave = OpenSpectraHeader.BIP_INTERLEAVE
        elif interleave == OpenSpectraHeader.BSQ_INTERLEAVE:
            self.__interleave = OpenSpectraHeader.BSQ_INTERLEAVE
        elif interleave == OpenSpectraHeader.BIL_INTERLEAVE:
            self.__interleave = OpenSpectraHeader.BIL_INTERLEAVE
        else:
            raise OpenSpectraHeaderError("Unknown interleave format in header file.  Value is: {0}".
                format(self.__props.get(OpenSpectraHeader._INTERLEAVE)))

        self.__samples = int(self.__props[OpenSpectraHeader._SAMPLES])
        self.__lines = int(self.__props[OpenSpectraHeader._LINES])
        self.__band_count = int(self.__props[OpenSpectraHeader._BANDS])

        if self.__samples is None or self.__samples <= 0:
            raise OpenSpectraHeaderError("Value for 'samples' in header is not valid: {0}"
                .format(self.__samples))

        if self.__lines is None or self.__lines <= 0:
            raise OpenSpectraHeaderError("Value for 'lines' in header is not valid: {0}"
                .format(self.__lines))

        if self.__band_count is None or self.__band_count <= 0:
            raise OpenSpectraHeaderError("Value for 'bands' in header is not valid: {0}"
                .format(self.__band_count))

        band_names = self.__props.get(OpenSpectraHeader._BAND_NAMES)
        wavelengths_str = self.__props.get(OpenSpectraHeader._WAVELENGTHS)

        # possible to have only bands or wavelenghts or both or neither
        if band_names is None:
            band_names = ["Band " + index for index in np.arange(
                1, self.__band_count + 1, 1, np.int16).astype(str)]
        else:
            if len(band_names) != self.__band_count:
                raise OpenSpectraHeaderError(
                    "Number of 'band names' {0} does not match number of bands {1}".
                        format(len(band_names), self.__band_count))

        if wavelengths_str is None:
            wavelengths_str = np.arange(
                1, self.__band_count + 1, 1, np.float64).astype(str)
        else:
            if len(wavelengths_str) != self.__band_count:
                raise OpenSpectraHeaderError(
                    "Number of wavelengths {0} does not match number of bands {1}".
                        format(len(wavelengths_str), self.__band_count))

        self.__wavelengths = np.array(wavelengths_str, np.float64)
        self.__band_labels = list(zip(band_names, wavelengths_str))

        self.__header_offset = int(self.__props[OpenSpectraHeader.__HEADER_OFFSET])
        # TODO missing sometimes??
        if OpenSpectraHeader.__REFLECTANCE_SCALE_FACTOR in self.__props:
            self.__reflectance_scale_factor = np.float64(
                self.__props[OpenSpectraHeader.__REFLECTANCE_SCALE_FACTOR])

        # map info = {UTM, 1.000, 1.000, 620006.407, 2376995.930, 7.8000000000e+000, 7.8000000000e+000,
        #               4, North, WGS-84, units=Meters, rotation=29.00000000}
        map_info_list = self.__props.get(OpenSpectraHeader._MAP_INFO)
        if map_info_list is not None:
            self.__map_info:OpenSpectraHeader.MapInfo = OpenSpectraHeader.MapInfo(map_info_list)
        else:
            OpenSpectraHeader.__LOG.info("Optional map info section not found")

        data_type = self.__props.get(OpenSpectraHeader.__DATA_TYPE)
        if data_type not in OpenSpectraHeader.__DATA_TYPE_DIC:
            raise OpenSpectraHeaderError("Specified 'data type' not recognized, value was: {0}".format(data_type))

        interleave = self.__props.get(OpenSpectraHeader._INTERLEAVE)
        if not (interleave == OpenSpectraHeader.BIL_INTERLEAVE or
            interleave == OpenSpectraHeader.BIP_INTERLEAVE or
            interleave == OpenSpectraHeader.BSQ_INTERLEAVE):
            raise OpenSpectraHeaderError("Specified 'interleave' not recognized, value was: {0}".format(interleave))

        description = self.__props.get(OpenSpectraHeader.__DESCRIPTION)
        if len(description) > 0:
            self.__description = " ".join(description)

        data_ignore_value = self.__props.get(OpenSpectraHeader.__DATA_IGNORE_VALUE)
        if data_ignore_value is not None:
            if re.match("[+-]?[0-9]*", data_ignore_value):
                self.__data_ignore_value = int(data_ignore_value)
            elif re.match("[+-]?[0-9]*[\.][0-9]*", data_ignore_value):
                self.__data_ignore_value = float(data_ignore_value)
            else:
                raise OpenSpectraHeaderError("Couldn't parse 'data ignore value' as a float or int, value was: {0}", data_ignore_value)

        default_stretch:str = self.__props.get(OpenSpectraHeader.__DEFAULT_STRETCH)
        self.__default_stretch = LinearImageStretch.create_default_stretch(default_stretch)

        bad_band_list:list = self.__props.get(OpenSpectraHeader._BAD_BAND_LIST)
        if bad_band_list is not None:
            if len(bad_band_list) != self.__band_count:
                raise OpenSpectraHeaderError("Bad band list, 'bbl' length did not match band count")

            if not all(item == "0" or item == "1" for item in bad_band_list):
                raise OpenSpectraHeaderError("Bad band list 'bbl' should only have value of 0 or 1, list is: {0}".format(bad_band_list))

            # remember that "1" means the band is good, "0" means it's bad so
            # but True in a numpy mask means the value is masked so flip the values
            self.__bad_band_list = [not bool(int(item)) for item in bad_band_list]

        # TODO byte_order - make sure we recognize and support?
        # TODO additional validation????


class MutableOpenSpectraHeader(OpenSpectraHeader):

    __LOG:Logger = LogHelper.logger("MutableOpenSpectraHeader")

    def __init__(self, source_file_name:str=None, os_header:OpenSpectraHeader=None):
        # Could initialize with neither but for now we don't support creating an entire header from scratch
        if source_file_name is None and os_header is None:
            raise OpenSpectraHeaderError(
                "Creating a MutableOpenSpectraHeader requires starting with a file or another OpenSpectra header")

        if source_file_name is not None:
            super().__init__(source_file_name)
            super().load()
        else:
            self._set_props(os_header._copy_props())

    @staticmethod
    def __convert_bool_value(value:bool) -> str:
        # Maintain the naming convention that a False, meaning not masked or good band, is a '1'
        # in the header file and '0' is True
        if value:
            return "0"
        else:
            return "1"

    def load(self):
        # prevent load from being called
        pass

    def save(self):
        # TODO implement writing file here??  Need new file name
        pass

    def set_lines(self, lines:int):
        self._update_prop(self._LINES, lines)

    def set_samples(self, samples:int):
        self._update_prop(self._SAMPLES, samples)

    def set_bands(self, bands_names:List[str], wavelengths:np.ndarray, bad_bands:List[bool]=None):
        if len(wavelengths.shape) != 1:
            raise OpenSpectraHeaderError("wave_lengths should be one dimensional")

        band_count = len(bands_names)

        self._update_prop(self._BANDS, band_count, False)
        self._update_prop(self._BAND_NAMES, bands_names, False)
        if bad_bands is not None:
            self._update_prop(self._BAD_BAND_LIST,
                [MutableOpenSpectraHeader.__convert_bool_value(bad_band) for bad_band in bad_bands],
                False)
        self._update_prop(self._WAVELENGTHS, wavelengths)

    def set_interleave(self, interleave:str):
        self._update_prop(self._INTERLEAVE, interleave)

    def set_x_reference(self, x_pixel:float, x_cooridinate:float):
        map_info = self.map_info()
        if map_info is not None:
            map_info_list = self._get_prop(self._MAP_INFO)
            map_info_list[1] = str(x_pixel)
            map_info_list[3] = str(x_cooridinate)
            self._update_prop(self._MAP_INFO, map_info_list)

    def set_y_reference(self, y_pixel:float, y_cooridinate:float):
        map_info = self.map_info()
        if map_info is not None:
            map_info_list = self._get_prop(self._MAP_INFO)
            map_info_list[2] = str(y_pixel)
            map_info_list[4] = str(y_cooridinate)
            self._update_prop(self._MAP_INFO, map_info_list)


class Shape:

    def __init__(self, x, y, z):
        self.__shape = (x, y, z)
        self.__size = x * y * z

    def shape(self) -> (int, int, int):
        return self.__shape

    def size(self) -> int:
        return self.__size

    def lines(self) -> int:
        pass

    def samples(self) -> int:
        pass

    def bands(self) -> int:
        pass


class BILShape(Shape):

    def __init__(self, lines, samples, bands):
        super().__init__(lines, bands, samples)

    def lines(self) -> int:
        return self.shape()[0]

    def samples(self) -> int:
        return self.shape()[2]

    def bands(self) -> int:
        return self.shape()[1]


class BQSShape(Shape):

    def __init__(self, lines, samples, bands):
        super().__init__(bands, lines, samples)

    def lines(self) -> int:
        return self.shape()[1]

    def samples(self) -> int:
        return self.shape()[2]

    def bands(self) -> int:
        return self.shape()[0]


class BIPShape(Shape):

    def __init__(self, lines, samples, bands):
        super().__init__(lines, samples, bands)

    def lines(self) -> int:
        return self.shape()[0]

    def samples(self) -> int:
        return self.shape()[1]

    def bands(self) -> int:
        return self.shape()[2]


class FileModel:

    def __init__(self, path:Path, header:OpenSpectraHeader):
        self._file:np.ndarray = None
        self._path = path
        self._offset:int = header.header_offset()

        # size in bytes of each data element in the file
        self._data_type = np.dtype(header.data_type())

        # TODO set based on byte_order from header but doesn't seem to make a difference
        self._data_type.newbyteorder("L")
        # data_type.newbyteorder("B")

    def load(self, shape:Shape):
        pass

    def file(self) -> np.ndarray:
        return self._file

    def name(self):
        return self._path.name

    def data_type(self):
        return self._file.dtype

    def _validate(self, shape:Shape):
        if self._file.size != shape.size():
            raise OpenSpectraFileError("Expected {0} data points but found {1}".
                format(shape.size(), self._file.size))


class CubeSliceArgs():

    def __init__(self, lines:Tuple[int, int], samples:Tuple[int, int], bands:Union[Tuple[int, int], List[int]]):
        self.__line_arg = slice(lines[0], lines[1])
        self.__sample_arg = slice(samples[0], samples[1])

        self.__band_arg = None
        if isinstance(bands, Tuple):
            self.__band_arg = slice(bands[0], bands[1])
        elif isinstance(bands, List):
            self.__band_arg = bands

    def line_arg(self) -> slice:
        return self.__line_arg

    def sample_arg(self) -> slice:
        return self.__sample_arg

    def band_arg(self) -> Union[slice, List[int]]:
        return self.__band_arg


class FileTypeDelegate:

    def __init__(self, shape:Shape, file_model:FileModel):
        self.__shape = shape
        self._file_model = file_model

    def image(self, band:Union[int, tuple]) -> np.ndarray:
        """bands are zero based here with a max value of len(band) - 1
        It's important to understand that selecting images with an int index
        returns a view of the underlying data while using a tuple returns a copy.
        See https://docs.scipy.org/doc/numpy/reference/arrays.indexing.html
        for more details"""
        pass

    def bands(self, line:Union[int, tuple, np.ndarray], sample:Union[int, tuple, np.ndarray]) -> np.ndarray:
        """lines and samples are zero based here with a max value of len(line) - 1
        It's important to understand that selecting images with an int index
        returns a view of the underlying data while using a tuple or ndarray returns a copy.
        See https://docs.scipy.org/doc/numpy/reference/arrays.indexing.html
        for more details"""
        pass

    def cube(self, lines:Tuple[int, int], samples:Tuple[int, int],
            bands:Union[Tuple[int, int], List[int]]) -> np.ndarray:
        """Return a sub-cube or the whole data cube depending on the argument values.
        lines, samples and bands are zero based here and work like the standard python and numpy slicing.
        lines and samples should be a tuple of integers where line[0] is the start line and
        line[1] is the end line and the last line included will be line[1] - 1.  So the valid range
        for lines is 0 to the line count defined the in the files header.
        The same applies for samples. lines and samples are then selected contiguously
        from the start value to the end value - 1.  Bands can be a tuple of 2 integers indicating the start and end
        bands as with lines and samples or a list of contiguous or non-contiguous integers to be selected.  To select
        a single band with index of i pass a tuple of the form (i, i + 1).
        Using the start and end option for selecting contiguous bands will be more efficient since it will result
        in a numpy view being returned while the other two options result in a copy being returned.  See
        https://docs.scipy.org/doc/numpy/reference/arrays.indexing.html for more information"""
        pass

    def shape(self) -> Shape:
        return self.__shape


class BILFileDelegate(FileTypeDelegate):
    """An 'interleave': 'bil' file"""

    def __init__(self, header:OpenSpectraHeader, file_model:FileModel):
        # inspect header info to make sure it's what we expect
        if header.interleave() != OpenSpectraHeader.BIL_INTERLEAVE:
            raise OpenSpectraFileError("Expected a file with interleave type 'bil' got {0}".
                format(header.interleave()))

        super().__init__(
            BILShape(header.lines(), header.samples(), header.band_count()), file_model)

    def image(self, band:Union[int, tuple]) -> np.ndarray:
        """It's important to understand that selecting images with an int index
        returns a view of the underlying data while using a tuple returns a copy.
        See https://docs.scipy.org/doc/numpy/reference/arrays.indexing.html
        for more details"""
        return self._file_model.file()[:, band, :]

    def bands(self, line:Union[int, tuple, np.ndarray], sample:Union[int, tuple, np.ndarray]) -> np.ndarray:
        """It's important to understand that selecting images with an int index
        returns a view of the underlying data while using a tuple or ndarray returns a copy.
        See https://docs.scipy.org/doc/numpy/reference/arrays.indexing.html
        for more details"""
        return self._file_model.file()[line, :, sample]

    def cube(self, lines:Tuple[int, int], samples:Tuple[int, int],
            bands:Union[Tuple[int, int], List[int]]) -> np.ndarray:
        args = CubeSliceArgs(lines, samples, bands)
        return self._file_model.file()[args.line_arg(), args.band_arg(), args.sample_arg()]


class BQSFileDelegate(FileTypeDelegate):
    """An 'interleave': 'bsq' file"""

    def __init__(self, header:OpenSpectraHeader, file_model:FileModel):
        # inspect header info to make sure it's what we expect
        if header.interleave() != OpenSpectraHeader.BSQ_INTERLEAVE:
            raise OpenSpectraFileError("Expected a file with interleave type 'bsq' got {0}".
                format(header.interleave()))

        super().__init__(
            BQSShape(header.lines(), header.samples(), header.band_count()), file_model)

    def image(self, band:Union[int, tuple]) -> np.ndarray:
        """It's important to understand that selecting images with an int index
        returns a view of the underlying data while using a tuple returns a copy.
        See https://docs.scipy.org/doc/numpy/reference/arrays.indexing.html
        for more details"""
        return self._file_model.file()[band, :, :]

    def bands(self, line:Union[int, tuple, np.ndarray], sample:Union[int, tuple, np.ndarray]) -> np.ndarray:
        """It's important to understand that selecting images with an int index
        returns a view of the underlying data while using a tuple or ndarray returns a copy.
        See https://docs.scipy.org/doc/numpy/reference/arrays.indexing.html
        for more details"""
        return self._file_model.file()[:, line, sample]

    def cube(self, lines:Tuple[int, int], samples:Tuple[int, int],
            bands:Union[Tuple[int, int], List[int]]) -> np.ndarray:
        args = CubeSliceArgs(lines, samples, bands)
        return self._file_model.file()[args.band_arg(), args.line_arg(), args.sample_arg()]


class BIPFileDelegate(FileTypeDelegate):
    """An 'interleave': 'bip' file"""

    def __init__(self, header:OpenSpectraHeader, file_model:FileModel):
        # inspect header info to make sure it's what we expect
        if header.interleave() != OpenSpectraHeader.BIP_INTERLEAVE:
            raise OpenSpectraFileError("Expected a file with interleave type 'bip' got {0}".
                format(header.interleave()))

        super().__init__(
            BIPShape(header.lines(), header.samples(), header.band_count()), file_model)

    def image(self, band:Union[int, tuple]) -> np.ndarray:
        """It's important to understand that selecting images with an int index
        returns a view of the underlying data while using a tuple returns a copy.
        See https://docs.scipy.org/doc/numpy/reference/arrays.indexing.html
        for more details"""
        return self._file_model.file()[:, :, band]

    def bands(self, line:Union[int, tuple, np.ndarray], sample:Union[int, tuple, np.ndarray]) -> np.ndarray:
        """It's important to understand that selecting images with an int index
        returns a view of the underlying data while using a tuple or ndarray returns a copy.
        See https://docs.scipy.org/doc/numpy/reference/arrays.indexing.html
        for more details"""
        return self._file_model.file()[line, sample, :]

    def cube(self, lines:Tuple[int, int], samples:Tuple[int, int],
            bands:Union[Tuple[int, int], List[int]]) -> np.ndarray:
        args = CubeSliceArgs(lines, samples, bands)
        return self._file_model.file()[args.line_arg(), args.sample_arg(), args.band_arg()]


class MemoryModel(FileModel):

    def __init__(self, path:Path, header: OpenSpectraHeader):
        super().__init__(path, header)

    def load(self, shape:Shape):
        self._file = np.array([], self._data_type)
        with self._path.open("rb") as file:
            file.seek(self._offset)
            bytes_in = file.read()
            while bytes_in:
                self._file = np.append(self._file, np.frombuffer(bytes_in, self._data_type))
                bytes_in = file.read()

        self._validate(shape)
        self._file = self._file.reshape(shape.shape())


class MappedModel(FileModel):

    def __init__(self, path:Path, header:OpenSpectraHeader):
        super().__init__(path, header)

    def load(self, shape:Shape):
        self._file = np.memmap(self._path, dtype = self._data_type, mode = 'r',
            offset=self._offset, shape = shape.shape())
        self._validate(shape)


class OpenSpectraFile:

    __LOG:Logger = LogHelper.logger("OpenSpectraFile")

    def __init__(self, header:OpenSpectraHeader, file_delegate:FileTypeDelegate,
            memory_model:FileModel):
        self.__header = header
        self.__memory_model = memory_model
        self.__file_delegate = file_delegate
        self.__validate()

        if OpenSpectraFile.__LOG.isEnabledFor(logging.DEBUG):
            # TODO seems a little weird, maybe the file delegate should provide access to the file?
            # TODO so how far do we want to go with the delegate, expose file?  Only expose file props/methods?
            OpenSpectraFile.__LOG.debug("Shape: {0}", self.__memory_model.file().shape)
            OpenSpectraFile.__LOG.debug("NDim: {0}", self.__memory_model.file().ndim)
            OpenSpectraFile.__LOG.debug("Size: {0}", self.__memory_model.file().size)
            OpenSpectraFile.__LOG.debug("Type: {0}", self.__memory_model.file().dtype)

            # TODO so this causes performance problems on large file even with memory mapped, probably has to read the whole file
            # TODO doesn't consume a bunch of memory in the end.
            # OpenSpectraFile.__LOG.debug("Min: {0}, Max: {1}", self.__memory_model.file().min(), self.__memory_model.file().max())

        # TODO this causes all memory to get used up then released and takes a long time but works when copy=False
        # TODO doesn't seem to recover at all if copy=True
        # view = np.ma.masked_invalid(self.__memory_model.file(), False)
        # view = np.ma.masked_outside(view, -1, 1, False)
        # OpenSpectraFile.__LOG.debug("Filtered Min: {0}, Max: {1}, Size: {2}", view.min(), view.max(), view[~view.mask].size)

    def raw_image(self, band:Union[int, tuple]) -> np.ndarray:
        """Return the image data for the given band.
        It's important to understand that selecting images with an int index
        returns a view of the underlying data while using a tuple returns a copy.
        See https://docs.scipy.org/doc/numpy-1.16.0/user/basics.indexing.html
        for more details"""
        return self.__file_delegate.image(band)

    def bands(self, line:Union[int, tuple, np.ndarray], sample:Union[int, tuple, np.ndarray]) -> np.ndarray:
        """Return all of the band values for a given pixel.  The number of lines and samples passed needs
        to be the same.  The array returned will have a shape of (number of lines & samples, number of bands)
        It's important to understand that selecting bands with an int index
        returns a view of the underlying data while using a tuple or ndarray returns a copy.
        See https://docs.scipy.org/doc/numpy-1.16.0/user/basics.indexing.html
        for more details"""
        self.__validate_band_args(line, sample)
        bands = self.__file_delegate.bands(line, sample)

        # If the arguments were single ints the array of bands will be one
        # dimensional so reshape it so it's consistent with multi-point results
        if len(bands.shape) == 1:
            bands = bands.reshape(1, bands.size)
        return bands

    def cube(self, lines:Tuple[int, int], samples:Tuple[int, int],
            bands:Union[Tuple[int, int], List[int]]) -> np.ndarray:
        return self.__file_delegate.cube(lines, samples, bands)

    def name(self) -> str:
        return self.__memory_model.name()

    def header(self) -> OpenSpectraHeader:
        return self.__header

    def __validate(self):
        if self.__memory_model.data_type() != self.__header.data_type():
            raise TypeError("Header file type {0}, does not match actually data type {1}",
                self.__header.data_type(), self.__memory_model.data_type())

    def __validate_band_args(self, line:Union[int, tuple, np.ndarray], sample:Union[int, tuple, np.ndarray]):
        if isinstance(line, int) and isinstance(sample, int):
            pass
        elif isinstance(line, tuple) and isinstance(sample, tuple):
            if len(line) != len(sample):
                raise ValueError("tuple arguments must have the same length")

        elif isinstance(line, np.ndarray) and isinstance(sample, np.ndarray):
            if line.ndim != 1 or sample.ndim != 1:
                raise ValueError("ndarray arguments must have a dimension of 1")

            if line.size != sample.size:
                raise ValueError("ndarray arguments must have the same size")

        else:
            raise TypeError("'line' and 'sample' arguments must have the same type")


class OpenSpectraFileFactory:
    """An object oriented way to create an OpenSpectra file"""

    __LOG: logging.Logger = LogHelper.logger("OpenSpectraFileFactory")

    MEMORY_MODEL:int = 0
    MAPPED_MODEL:int = 1

    @staticmethod
    def create_open_spectra_file(file_name, model=MAPPED_MODEL) -> OpenSpectraFile:
        path = Path(file_name)

        if path.exists() and path.is_file():
            OpenSpectraFileFactory.__LOG.info("Opening {0} with mode {1}", path.name, path.stat().st_mode)

            header = OpenSpectraHeader(file_name + ".hdr")
            header.load()
            file_type = header.interleave()

            memory_model = None
            if model == OpenSpectraFileFactory.MEMORY_MODEL:
                memory_model = MemoryModel(path, header)
            else:
                memory_model:FileModel = MappedModel(path, header)

            if file_type == OpenSpectraHeader.BIL_INTERLEAVE:
                file_delegate = BILFileDelegate(header, memory_model)
            elif file_type == OpenSpectraHeader.BSQ_INTERLEAVE:
                file_delegate = BQSFileDelegate(header, memory_model)
            elif file_type == OpenSpectraHeader.BIP_INTERLEAVE:
                file_delegate = BIPFileDelegate(header, memory_model)
            else:
                raise OpenSpectraHeaderError("Unexpected file type: {0}".format(file_type))

            # TODO this is kind of weird
            memory_model.load(file_delegate.shape())
            return OpenSpectraFile(header, file_delegate, memory_model)

        else:
            raise OpenSpectraFileError("File {0} not found".format(path))


def create_open_spectra_file(file_name, model=OpenSpectraFileFactory.MAPPED_MODEL) -> OpenSpectraFile:
    """A function based way to create an OpenSpectra file"""

    return OpenSpectraFileFactory.create_open_spectra_file(file_name, model)


class OpenSpectraHeaderError(Exception):
    """Raised when there's a problem with the header file"""
    pass


class OpenSpectraFileError(Exception):
    """Raised when there's a problem with the data file"""
    pass

