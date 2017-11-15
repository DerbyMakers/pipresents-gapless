# based on pp_gpiodriver

import time
import copy
import os
import ConfigParser
from pp_utils import Monitor


class pp_mpr121driver(object):
    """
    pp_mpr121driver provides mpr121 IO facilties for Pi presents
     - configures and binds mpr121 IO pins from data in .cfg file
     - reads input pins, provides callbacks on state changes which
       generate input events
     - TODO - changes the state of output pins as required by calling
       programs

    WIP - will be starting with capacitive inputs only as that's all
    the mpr121 libs currently support. Support for general input and
    output will be added once the libs support it.

    Overview of MPR121
    * i2c IO chip with capacitive sensing capabilities
    * 12 pins plus a virtual 13th Eleprox for proximity based on
      agregate of others
    * 0-3 are input only. 4-12 can also be used as outputs capable of
      driving an LED.
    * interrupt on state change, unused by current libs

    Things we can set on the mpr121 - many of which are unsupported or
    not exposed by the libs:

    General:
        Address - 0x5A, 0x5B, 0x5C, 0x5D
        Debounce Touch, Debounce Release - 0-7, used by all 13
            channels on chip
        Filter, global CDC and CDT. Not exposed by libs.

    Per pin:
        Touch Threshold, Release Threshold - 00-FF, typically
            0x04-0x10, touch > release. NOTE: the lib currently sets
            this as a global
        CDC,CDT - set 0 to use global, or to value - see datasheet.
            NOTE; not exposed by libs
        IO Config NOT exposed by libs yet:
        * enable
        * direction - in/out
        * crtl0/1 - mode settings like floating, pull up/down,
          CMOS out, open drain high/low side

    Exposed by current libs:
    * Address - requires a separate lib instance per address
    * Thresholds - on a globabl basis per chip
    * capacitive input state

    """


# constants for buttons

# configuration from mpr121.cfg
# FIXME - decide what needs to be in here, and update the template
# below accordingly. These are internally used indexes into the
# template, not directly related to the config file. May be worth
# keeping similar to the gpiodriver one for familiarity to users.

    PIN = 0             # pin on RPi board GPIO connector e.g. P1-11
    DIRECTION = 1       # TOUCH/IN/OUT/NONE (None is not used)
    NAME = 2            # symbolic name for output
    RISING_NAME = 3     # symbolic name for rising edge callback
    FALLING_NAME = 4    # symbolic name of falling edge callback
    ONE_NAME = 5        # symbolic name for one state callback
    ZERO_NAME = 6       # symbolic name for zero state callback
    REPEAT = 7          # repeat interval for state callbacks (mS)
    THRESHOLD = 8       # threshold of debounce count for state change to be considered
    PULL = 9            # pull up or down or none
    LINKED_NAME = 10    # output pin that follows the input
    LINKED_INVERT = 11  # invert the linked pin


# dynamic data
    COUNT = 12          # variable - count of the number of times the input has been 0 (limited to threshold)
    PRESSED = 13        # variable - debounced state
    LAST = 14           # varible - last state - used to detect edge
    REPEAT_COUNT = 15

    TEMPLATE = ['',                     # pin
                '',                     # direction
                '',                     # name
                '', '', '', '',         # input names
                0,                      # repeat
                0,                      # threshold
                '',                     # pull
                -1,                     # linked pin
                False,                  # linked invert
                0, False, False, 0]     # dynamics

# strings to use in config to refer to chip by hex address
    ADDRSTRING = {
        0x5A: '5A',
        0x5B: '5B',
        0x5C: '5C',
        0x5D: '5D',
        }


# CLASS VARIABLES  (pp_mpr121driver.)
    pins = {}
    driver_active = False
    title = ''

    # executed by main program and by each object using gpio
    def __init__(self):
        self.mon = Monitor()

    # executed once from main program
    def init(self, filename, filepath, widget, button_callback=None):

        # instantiate arguments
        self.widget = widget
        self.filename = filename
        self.filepath = filepath
        self.button_callback = button_callback
        self.mpr121 = {}
        self.last_touched = {}  # TODO: decide whether this is better than the pin LAST and remove one or other
        pp_mpr121driver.driver_active = False

        # read gpio.cfg file.
        reason, message = self._read(self.filename, self.filepath)
        if reason == 'error':
            return 'error', message
        if self.config.has_section('DRIVER') is False:
            return 'error', 'No DRIVER section in ' + self.filepath

        # read information from DRIVER section
        pp_mpr121driver.title = self.config.get('DRIVER', 'title')
        button_tick_text = self.config.get('DRIVER', 'tick-interval')
        if button_tick_text.isdigit():
            if int(button_tick_text) > 0:
                self.button_tick = int(button_tick_text)  # in mS
            else:
                return 'error', 'tick-interval is not a positive integer'
        else:
            return 'error', 'tick-interval is not an integer'

        import Adafruit_MPR121.MPR121 as MPR121
        for address in [0x5A, 0x5B, 0x5C, 0x5D]:
            try:
                enabled = self.config.getboolean(
                    'DRIVER', pp_mpr121driver.ADDRSTRING[address])
                if enabled:
                    self.mpr121[address] = MPR121.MPR121()
            except (ValueError, ConfigParser.NoOptionError) as e:
                pass

        # construct the GPIO/capacitive control list from the configuration
        for address, mpr121 in self.mpr121.iteritems():
            pp_mpr121driver.pins[address] = {}
            for idx in range(12):
                pin = copy.deepcopy(pp_mpr121driver.TEMPLATE)
                pin[pp_mpr121driver.PIN] = idx
                pin_def = pp_mpr121driver.ADDRSTRING[address] + '-{0}'.format(idx)
                if (self.config.has_section(pin_def) is False) or (self.config.has_option(pin_def, 'direction') is False):
                    self.mon.warn(self, "no pin definition for " + pin_def)
                    pin[pp_mpr121driver.DIRECTION] = 'none'
                else:
                    # direction
                    direction = self.config.get(pin_def, 'direction')
                    if direction == 'touch':
                        pin[pp_mpr121driver.DIRECTION] = direction
                        if self.config.has_option(pin_def,
                                                  'rising-name'):
                            pin[pp_mpr121driver.RISING_NAME] = \
                                self.config.get(pin_def, 'rising-name')
                        if self.config.has_option(pin_def,
                                                  'falling-name'):
                            pin[pp_mpr121driver.FALLING_NAME] = \
                                self.config.get(pin_def, 'falling-name')
                    # TODO: else if direction == 'in': etc. when driver allows
                    else:
                        pin[pp_mpr121driver.DIRECTION] = 'none'

                pp_mpr121driver.pins[address][idx] = copy.deepcopy(pin)

        # set up the GPIO inputs and outputs
        for address, mpr121 in self.mpr121.iteritems():
            if mpr121.begin(address=address):
                try:
                    touch_threshold = self.config.getint(
                        pp_mpr121driver.ADDRSTRING[address],
                        'touch_threshold')
                    release_threshold = self.config.getint(
                        pp_mpr121driver.ADDRSTRING[address],
                        'release_threshold')
                    if ((touch_threshold >= 0) and
                            (touch_threshold <= 255) and
                            (release_threshold >= 0) and
                            (release_threshold <= 255)):
                        mpr121.set_thresholds(touch_threshold,
                                              release_threshold)
                except (ValueError,
                        ConfigParser.NoOptionError,
                        ConfigParser.NoSectionError) as e:
                    pass
            else:
                # FIXME: check how logging/error reporting works in
                # pipresents so we can do something suitable here
                pass

        pp_mpr121driver.driver_active = True

        # init last_touched
        for address, mpr121 in self.mpr121.iteritems():
            self.last_touched[address] = mpr121.touched()

        # init timer
        self.button_tick_timer = None
        return 'normal', pp_mpr121driver.title + ' active'

    # called by main program only
    def start(self):
        # loop to look at the buttons
        self._do_buttons()
        self.button_tick_timer = self.widget.after(self.button_tick, self.start)

    # called by main program only
    def terminate(self):
        if pp_mpr121driver.driver_active is True:
            if self.button_tick_timer is not None:
                self.widget.after_cancel(self.button_tick_timer)
            self._reset_outputs()

# ************************************************
# gpio input functions
# called by main program only
# ************************************************

    def _reset_input_state(self):
        for pin in pp_mpr121driver.pins:
            pin[pp_mpr121driver.COUNT] = 0
            pin[pp_mpr121driver.PRESSED] = False
            pin[pp_mpr121driver.LAST] = False
            pin[pp_mpr121driver.REPEAT_COUNT] = pin[pp_mpr121driver.REPEAT]

    def _do_buttons(self):
        for address, mpr121 in self.mpr121.iteritems():
            current_touched = mpr121.touched()
            for i in range(12):
                # Each pin is represented by a bit in the touched value.  A value of 1
                # means the pin is being touched, and 0 means it is not being touched.
                pin_bit = 1 << i
                if pp_mpr121driver.pins[address][i][pp_mpr121driver.DIRECTION] in ('touch',):
                    # First check if transitioned from not touched to touched.
                    if (current_touched & pin_bit) and not (self.last_touched[address] & pin_bit):
                        print('{0} touched!'.format(i))
                        if self.button_callback is not None and pp_mpr121driver.pins[address][i][pp_mpr121driver.RISING_NAME] != '':
                            self.button_callback(
                                pp_mpr121driver.pins[address][i][pp_mpr121driver.RISING_NAME],
                                pp_mpr121driver.title)
                    # Next check if transitioned from touched to not touched.
                    if not current_touched & pin_bit and self.last_touched[address] & pin_bit:
                        if self.button_callback is not None and pp_mpr121driver.pins[address][i][pp_mpr121driver.FALLING_NAME] != '':
                            self.button_callback(
                                pp_mpr121driver.pins[address][i][pp_mpr121driver.FALLING_NAME],
                                pp_mpr121driver.title)
                        print('{0} released!'.format(i))

            self.last_touched[address] = current_touched

# ************************************************
# gpio output interface methods
# these can be called from many classes so need to operate on class variables
# ************************************************

    # execute an output event

    def handle_output_event(self, name, param_type, param_values, req_time):
        # TODO: implement output handling when libs allow
        return 'normal', pp_mpr121driver.title + ' Output events not yet supported.'

    def _reset_outputs(self):
        if pp_mpr121driver.driver_active is True:
            # TODO: implement when libs allow output
            pass

    def is_active(self):
        return pp_mpr121driver.driver_active

# ************************************************
# internal functions
# these can be called from many classes so need to operate on class variables
# ************************************************

    def _output_pin_of(self, name):
        # TODO: implement when libs allow output
        return -1


# ***********************************
# reading .cfg file
# ************************************

    def _read(self, filename, filepath):
        if os.path.exists(filepath):
            self.config = ConfigParser.ConfigParser()
            self.config.read(filepath)
            return 'normal', filename + ' read'
        else:
            return 'error', filename + ' not found at: ' + filepath


if __name__ == '__main__':
    from Tkinter import *

    def button_callback(symbol, source):
        print 'callback', symbol, source
        if symbol == 'pp-stop':
            idd.terminate()
            exit()
        pass

    root = Tk()

    w = Label(root, text="pp_mpr121driver.py test harness")
    w.pack()

    idd = pp_mpr121driver()
    reason, message = idd.init('mpr121.cfg',
                               '/home/pi/pipresents/pp_resources/pp_templates/mpr121.cfg',
                               root, button_callback)
    print reason, message
    idd.start()
    root.mainloop()
