#  Developed by Joseph M. Conti and Joseph W. Boardman on 1/21/19 6:29 PM.
#  Last modified 1/21/19 6:29 PM
#  Copyright (c) 2019. All rights reserved.

import logging

from PyQt5.QtCore import pyqtSlot, QObject, QRect, pyqtSignal, QChildEvent
from PyQt5.QtGui import QGuiApplication, QScreen, QImage, QColor
from PyQt5.QtWidgets import QTreeWidgetItem

from openspectra.image import Image, GreyscaleImage, RGBImage, Band
from openspectra.openspecrtra_tools import OpenSpectraHistogramTools, OpenSpectraBandTools, OpenSpectraImageTools, \
    RegionOfInterest
from openspectra.openspectra_file import OpenSpectraFile, OpenSpectraHeader
from openspectra.ui.bandlist import BandList, RGBSelectedBands
from openspectra.ui.imagedisplay import MainImageDisplayWindow, AdjustedMouseEvent, AreaSelectedEvent, \
    ZoomImageDisplayWindow
from openspectra.ui.plotdisplay import LinePlotDisplayWindow, HistogramDisplayWindow, LimitChangeEvent
from openspectra.ui.toolsdisplay import RegionOfInterestDisplayWindow, RegionStatsEvent, RegionToggleEvent, \
    RegionCloseEvent, RegionNameChangeEvent
from openspectra.utils import LogHelper, Logger


class RegionOfInterestManager(QObject):

    __LOG:Logger = LogHelper.logger("RegionOfInterestManager")

    stats_clicked = pyqtSignal(RegionStatsEvent)
    region_toggled = pyqtSignal(RegionToggleEvent)
    region_name_changed = pyqtSignal(RegionNameChangeEvent)
    region_closed =  pyqtSignal(RegionCloseEvent)
    window_closed = pyqtSignal()

    def __init__(self):
        super().__init__()
        # TODO figure out how to position the window??
        # Region of interest window
        self.__region_window = RegionOfInterestDisplayWindow()
        self.__region_window.region_toggled.connect(self.region_toggled)
        self.__region_window.region_name_changed.connect(self.region_name_changed)
        self.__region_window.stats_clicked.connect(self.stats_clicked)
        self.__region_window.region_closed.connect(self.region_closed)
        self.__region_window.closed.connect(self.__handle_window_closed)

        self.__regions = dict()

    def __del__(self):
        del self.__regions
        self.__region_window.close()
        self.__region_window = None

    def add_region(self, region:RegionOfInterest, color:QColor):
        self.__regions[region.id()] = region
        self.__region_window.add_item(region, color)

        if not self.__region_window.isVisible():
            self.__region_window.show()

    @pyqtSlot()
    def __handle_window_closed(self):
        self.__region_window.remove_all()
        self.__regions.clear()
        self.window_closed.emit()


class WindowManager(QObject):

    __LOG:Logger = LogHelper.logger("WindowManager")

    def __init__(self, band_list:BandList):
        super().__init__()
        screen:QScreen = QGuiApplication.primaryScreen()
        self.__screen_geometry:QRect = screen.geometry()

        WindowManager.__LOG.debug("Screen height: {0}, width: {1}",
            self.__screen_geometry.height(), self.__screen_geometry.width())

        # The available size is the size excluding window manager reserved areas such as task bars and system menus.
        self.__available_geometry:QRect = screen.availableGeometry()
        WindowManager.__LOG.debug("Available height: {0}, width: {1}",
            self.__available_geometry.height(), self.__available_geometry.width())

        self.__file_sets = dict()
        self.__band_list = band_list
        self.__band_list.bandSelected.connect(self.__handle_band_select)
        self.__band_list.rgbSelected.connect(self.__handle_rgb_select)

        self.__region_manager = RegionOfInterestManager()

    def __del__(self):
        # TODO This works but for some reason throws an exception on shutdown
        # TODO this broke again after upgrade, don't really need it
        # try:
        #    WindowManager.__LOG.debug("WindowManager.__del__ called...")
        # except Exception:
        #     pass

        del self.__file_sets
        del self.__regions
        self.__file_sets = None
        self.__band_list = None
        self.__screen_geometry = None
        self.__available_geometry = None

    def add_file(self, file:OpenSpectraFile):
        file_widget = self.__band_list.add_file(file)
        file_name = file_widget.text(0)

        if file_name in self.__file_sets:
            # TODO file names must be unique, handle dups somehow, no need to reopen really
            # TODO Just throw a up a dialog box saying it's already open?
            return

        file_set = FileManager(file, file_widget, self)
        self.__file_sets[file_name] = file_set

        if WindowManager.__LOG.isEnabledFor(logging.DEBUG):
            WindowManager.__LOG.debug("{0}", file.header().dump())

    # TODO - not used????
    def file(self, index=0) -> OpenSpectraFile:
        return self.__file_sets[index]

    def region_manager(self) -> RegionOfInterestManager:
        return self.__region_manager

    def screen_geometry(self) -> QRect:
        return self.__screen_geometry

    def available_geometry(self) -> QRect:
        return self.__available_geometry

    @pyqtSlot(QTreeWidgetItem)
    def __handle_band_select(self, item:QTreeWidgetItem):
        parent_item = item.parent()
        file_name = parent_item.text(0)
        if file_name in self.__file_sets:
            file_set = self.__file_sets[file_name]
            file_set.add_grey_window_set(
                parent_item.indexOfChild(item), item.text(0))
        else:
            # TODO report or log?
            pass

    @pyqtSlot(RGBSelectedBands)
    def __handle_rgb_select(self, bands:RGBSelectedBands):
        file_name = bands.file_name()
        if file_name in self.__file_sets:
            file_set = self.__file_sets[file_name]
            file_set.add_rgb_window_set(bands)
        else:
            # TODO report or log?
            pass


class FileManager(QObject):

    __LOG:Logger = LogHelper.logger("FileManager")

    def __init__(self, file:OpenSpectraFile, file_widget:QTreeWidgetItem,
                window_manager:WindowManager):
        super().__init__()
        self.__window_manager = window_manager
        self.__file = file
        self.__band_tools = OpenSpectraBandTools(self.__file)
        self.__image_tools = OpenSpectraImageTools(self.__file)
        self.__file_widget = file_widget
        self.__file_name = file_widget.text(0)
        self.__window_sets = list()

    def __del__(self):
        # TODO This works but for some reason throws an exception on shutdown
        # TODO this broke again after upgrade, don't really need it
        # try:
        #     FileManager.__LOG.debug("FileManager.__del__ called...")
        # except Exception:
        #     pass

        self.__window_sets = None
        self.__file_name = None
        self.__file_widget = None
        self.__band_tools = None
        self.__file = None
        self.__window_manager = None

    def add_rgb_window_set(self, bands:RGBSelectedBands):
        image = self.__image_tools.rgb_image(
            bands.red_index(), bands.green_index(), bands.blue_index(),
            bands.red_label(), bands.green_label(), bands.blue_label())
        self.__create_window_set(image)

    def add_grey_window_set(self, index:int, label:str):
        image = self.__image_tools.greyscale_image(index, label)
        self.__create_window_set(image)

    def header(self) -> OpenSpectraHeader:
        return self.__file.header()

    def band_tools(self):
        return self.__band_tools

    def window_manager(self) -> WindowManager:
        return self.__window_manager

    def __create_window_set(self, image:Image):
        title = self.__file_name + ": " + image.label()
        window_set = WindowSet(image, title, self)
        window_set.closed.connect(self.__handle_windowset_closed)
        self.__window_manager.region_manager().stats_clicked.connect(window_set.region_stats_handler)
        self.__window_manager.region_manager().region_toggled.connect(window_set.region_toogle_handler)
        self.__window_manager.region_manager().region_closed.connect(window_set.region_closed_handler)
        self.__window_manager.region_manager().region_name_changed.connect(window_set.region_name_changed_handler)

        # TODO need a layout manager
        y = 25
        if len(self.__window_sets) == 0:
            x = 300
        else:
            rect = self.__window_sets[len(self.__window_sets) - 1].get_image_window_geometry()
            x = rect.x() + rect.width() + 25

        window_set.init_position(x, y)
        self.__window_sets.append(window_set)

    @pyqtSlot(QChildEvent)
    def __handle_windowset_closed(self, event:QChildEvent):
        window_set = event.child()
        self.__window_sets.remove(window_set)
        FileManager.__LOG.debug("WindowSets open {0}", len(self.__window_sets))
        del window_set


class WindowSet(QObject):

    __LOG:Logger = LogHelper.logger("WindowSet")

    closed = pyqtSignal(QChildEvent)

    def __init__(self, image:Image, title:str, file_manager:FileManager):
        super().__init__()
        self.__file_manager = file_manager
        self.__image = image
        self.__title = title

        self.__histogram_tools = OpenSpectraHistogramTools(self.__image)
        self.__band_tools = file_manager.band_tools()

        self.__init_image_window()
        self.__init_plot_windows()

    def __init_image_window(self):
        if isinstance(self.__image, GreyscaleImage):
            self.__main_image_window = MainImageDisplayWindow(self.__image, self.__title,
                QImage.Format_Grayscale8, self.__file_manager.window_manager().available_geometry())
            self.__zoom_image_window = ZoomImageDisplayWindow(self.__image, self.__title,
                QImage.Format_Grayscale8, self.__file_manager.window_manager().available_geometry())
        elif isinstance(self.__image, RGBImage):
            self.__main_image_window = MainImageDisplayWindow(self.__image, self.__title,
                QImage.Format_RGB32, self.__file_manager.window_manager().available_geometry())
            self.__zoom_image_window = ZoomImageDisplayWindow(self.__image, self.__title,
                QImage.Format_RGB32, self.__file_manager.window_manager().available_geometry())
        else:
            raise TypeError("Image type not recognized, found type: {0}".
                format(type(self.__image)))

        self.__main_image_window.connect_zoom_window(self.__zoom_image_window)

        self.__main_image_window.pixel_selected.connect(self.__handle_pixel_click)
        self.__main_image_window.mouse_moved.connect(self.__handle_mouse_move)
        self.__main_image_window.closed.connect(self.__handle_image_closed)
        self.__main_image_window.area_selected.connect(self.__handle_area_selected)

        self.__zoom_image_window.pixel_selected.connect(self.__handle_pixel_click)
        self.__zoom_image_window.mouse_moved.connect(self.__handle_mouse_move)
        self.__zoom_image_window.area_selected.connect(self.__handle_area_selected)

    def __init_plot_windows(self):
        # setting the image_window as the parent causes the children to
        # close when image_window is closed but it doesn't destroy them
        # i.e. call __del__.  I think it's more intended from parents contain
        # their children not really among QMainWindows
        self.__spec_plot_window = LinePlotDisplayWindow(self.__main_image_window)

        self.__band_stats_window = LinePlotDisplayWindow(self.__main_image_window, "Band Stats")
        self.__file_manager.window_manager().region_manager().\
            window_closed.connect(self.__handle_region_window_close)

        self.__histogram_window = HistogramDisplayWindow(self.__main_image_window)
        self.__histogram_window.limit_changed.connect(self.__handle_hist_limit_change)

    def __del__(self):
        WindowSet.__LOG.debug("WindowSet.__del__ called...")
        self.__spec_plot_window = None
        self.__band_stats_window = None
        self.__histogram_window = None
        self.__zoom_image_window = None
        self.__main_image_window = None
        self.__file_manager = None
        self.__band_tools = None
        self.__histogram_tools = None
        self.__title = None
        self.__image = None

    def __init_histogram(self, x:int, y:int):
        if isinstance(self.__image, GreyscaleImage):
            raw_hist = self.__histogram_tools.raw_histogram()
            image_hist = self.__histogram_tools.adjusted_histogram()
            self.__histogram_window.create_plot_control(raw_hist, image_hist, Band.GREY)
        elif isinstance(self.__image, RGBImage):
            self.__histogram_window.create_plot_control(
                self.__histogram_tools.raw_histogram(Band.RED),
                self.__histogram_tools.adjusted_histogram(Band.RED), Band.RED)
            self.__histogram_window.create_plot_control(
                self.__histogram_tools.raw_histogram(Band.GREEN),
                self.__histogram_tools.adjusted_histogram(Band.GREEN), Band.GREEN)
            self.__histogram_window.create_plot_control(
                self.__histogram_tools.raw_histogram(Band.BLUE),
                self.__histogram_tools.adjusted_histogram(Band.BLUE), Band.BLUE)
        else:
            # TODO this shouldn't happen, throw something?
            WindowSet.__LOG.error("Window set has unknown image type")

        # TODO need some sort of layout manager?
        self.__histogram_window.setGeometry(x, y + self.get_image_window_geometry().height() + 50, 800, 400)
        self.__histogram_window.show()

    @pyqtSlot(AdjustedMouseEvent)
    def __handle_pixel_click(self, event:AdjustedMouseEvent):
        if self.__spec_plot_window.isVisible():
            plot_data = self.__band_tools.spectral_plot(event.pixel_y(), event.pixel_x())
            plot_data.color = "g"
            self.__spec_plot_window.add_plot(plot_data)

    @pyqtSlot(AdjustedMouseEvent)
    def __handle_mouse_move(self, event:AdjustedMouseEvent):
        plot_data = self.__band_tools.spectral_plot(event.pixel_y(), event.pixel_x())
        self.__spec_plot_window.plot(plot_data)

        if not self.__spec_plot_window.isVisible():
            # TODO need some sort of layout manager?
            rect = self.__histogram_window.geometry()
            self.__spec_plot_window.setGeometry(rect.x() + 50, rect.y() + 50, 500, 400)
            self.__spec_plot_window.show()

    @pyqtSlot()
    def __handle_image_closed(self):
        WindowSet.__LOG.debug("__handle_image_closed called...")
        self.__main_image_window = None

        self.__zoom_image_window.close()
        self.__zoom_image_window = None

        self.__histogram_window.close()
        self.__histogram_window = None

        self.__band_stats_window.close()
        self.__band_stats_window = None

        self.__spec_plot_window.close()
        self.__spec_plot_window = None

        self.closed.emit(QChildEvent(QChildEvent.ChildRemoved, self))

    @pyqtSlot()
    def __handle_region_window_close(self):
        self.__band_stats_window.clear()
        self.__band_stats_window.close()
        self.__main_image_window.remove_all_regions()
        self.__zoom_image_window.remove_all_regions()

    @pyqtSlot(LimitChangeEvent)
    def __handle_hist_limit_change(self, event:LimitChangeEvent):
        WindowSet.__LOG.debug("limit change event {0}, {1}", event.lower_limit(), event.upper_limit())
        updated:bool = False
        if event.has_upper_limit_change():
            self.__image.set_high_cutoff(event.upper_limit(), event.band())
            updated = True
            WindowSet.__LOG.debug("limit change event upper limit: {0}", event.upper_limit())

        if event.has_lower_limit_change():
            self.__image.set_low_cutoff(event.lower_limit(), event.band())
            updated = True
            WindowSet.__LOG.debug("Got limit change event lower limit: {0}", event.lower_limit())

        if updated:
            self.__image.adjust()

            # TODO use event instead?
            # trigger update in image window
            self.__main_image_window.refresh_image()
            self.__zoom_image_window.refresh_image()

            # TODO replotting the whole thing is bit inefficient?
            # TODO don't have the label here
            image_hist = self.__histogram_tools.adjusted_histogram(event.band())
            self.__histogram_window.set_adjusted_data(image_hist, event.band())
        else:
            WindowSet.__LOG.warning("Got limit change event with no limits")

    @pyqtSlot(AreaSelectedEvent)
    def __handle_area_selected(self, event:AreaSelectedEvent):
        region = event.area()
        self.__file_manager.window_manager().region_manager().add_region(region, event.color())

    def init_position(self, x:int, y:int):
        # TODO need some sort of layout manager?
        self.__main_image_window.move(x, y)
        self.__main_image_window.show()

        self.__zoom_image_window.move(x + 50, y + 50)
        self.__zoom_image_window.show()

        self.__init_histogram(x, y)

    def get_image_window_geometry(self):
        return self.__main_image_window.geometry()

    @pyqtSlot(RegionToggleEvent)
    def region_toogle_handler(self, event:RegionToggleEvent):
        self.__main_image_window.handle_region_toggle(event)
        self.__zoom_image_window.handle_region_toggle(event)

    @pyqtSlot(RegionStatsEvent)
    def region_stats_handler(self, event:RegionStatsEvent):
        self.__band_stats_window.clear()

        region = event.region()
        lines = region.adjusted_y_points()
        samples = region.adjusted_x_points()
        WindowSet.__LOG.debug("lines dim: {0}, samples dim: {1}", lines.ndim, samples.ndim)

        # TODO !!!! need to support multiple band stats windows!!!

        # TODO still??? bug here when image window has been resized, need adjusted coords
        stats_plot = self.__band_tools.statistics_plot(lines, samples, "Region name: {0}".format(region.name()))
        self.__band_stats_window.plot(stats_plot.mean())
        self.__band_stats_window.add_plot(stats_plot.min())
        self.__band_stats_window.add_plot(stats_plot.max())
        self.__band_stats_window.add_plot(stats_plot.plus_one_std())
        self.__band_stats_window.add_plot(stats_plot.minus_one_std())

        # TODO need some sort of layout manager?
        rect = self.__histogram_window.geometry()
        self.__band_stats_window.setGeometry(rect.x() + 75, rect.y() + 75, 500, 400)

        if not self.__band_stats_window.isVisible():
            self.__band_stats_window.show()

    @pyqtSlot(RegionCloseEvent)
    def region_closed_handler(self, event:RegionCloseEvent):
        self.__main_image_window.remove_region(event.region())
        self.__zoom_image_window.remove_region(event.region())

    @pyqtSlot(RegionNameChangeEvent)
    def region_name_changed_handler(self, event:RegionNameChangeEvent):
        name = event.region().name()
        WindowSet.__LOG.debug("new band stats title {0}: ", name)

        # TODO !!!!!!
        # TODO need to wire plot to Region so correct one is changed
        self.__band_stats_window.set_plot_title("Region name: {0}".format(name))
