from gi.repository import GLib
import phony.headset
import phony.base.ipc
import phony.base.log
import phony.audio.alsa
import phony.bluetooth.adapters
import phony.bluetooth.profiles.handsfree

from threading import Thread
from threading import Event
import queue as Queue
import sys, os, termios, tty, time, select


class KeyboardDialer(Thread):

    def __init__(self, headset):
        Thread.__init__(self)
        self.hs = headset
        self.phone_number = ""
        self.finish = False

    def isData(self):
        return select.select([self.stdin_fd], [], [], 0) == ([self.stdin_fd], [], [])

    def run(self):
        self.stdin_fd = sys.stdin.fileno()
        self.stdin_attrs = termios.tcgetattr(self.stdin_fd)
        tty.setcbreak(self.stdin_fd)
        while not self.finish:
            try:
                if self.isData():
                    char = os.read(self.stdin_fd, 1)
                    print("*")
                    sys.stdout.flush()
                    if char == chr(10):
                        # dial the number
                        if len(self.phone_number) > 0:
                            self.hs.dial_number(self.phone_number)
                            self.phone_number = ""
                    else:
                        if char.isdigit():
                            self.phone_number = self.phone_number + str(char)
                        else:
                            if char == 'd':
                                self.phone_number = ""
                            if char == 'q':
                                self.stop()
                                exit(0)
                            if char == 'a':
                                # answer call
                                self.hs.answer()
                            if char == 'h':
                                self.hs.hangup()
                time.sleep(0.1)
            except ValueError:
                print("Value Error")
                continue
            except SystemExit:
                termios.tcsetattr(self.stdin_fd, termios.TCSADRAIN, self.stdin_attrs)
                print("Cleaned up / Parent terminated normally")

    def stop(self):
        termios.tcsetattr(self.stdin_fd, termios.TCSADRAIN, self.stdin_attrs)
        self.finish = True
        self.hs.stop()


class ExampleHeadsetService:
    _hs = None
    _call_in_progress = False
    _ringer = False
    _dialer = None

    def device_connected(self):
        print('Device connected!')
        # get a keybord dialer running for making calls
        self._dialer = KeyboardDialer(self)
        self._dialer.run()

    def incoming_call(self, call):
        print(('Incoming call: %s' % call))
        if self._call_in_progress:
            self._hs.deflect_call_to_voicemail()
        else:
            # ring
            self._ringer = True

    def call_began(self, call):
        print(('Call began: %s' % call))
        # turn off ringer
        self._ringer = False
        self._call_in_progress = True

    def call_ended(self, call):
        print(('Call ended: %s' % call))
        self._call_in_progress = False

    def run(self):
        """
        Starts phony service which manages device pairing and setting
        up of hands-free profile services.  This function never returns.
        """
        bus = phony.base.ipc.BusProvider()

        # -1 find the first audio card that provides
        # audio input and output mixers.
        audio_card_index = -1

        with phony.bluetooth.adapters.Bluez5(bus) as adapter, \
                phony.bluetooth.profiles.handsfree.Ofono(bus) as hfp, \
                phony.audio.alsa.Alsa(card_index=audio_card_index) as audio, \
                phony.headset.HandsFreeHeadset(bus, adapter, hfp, audio) as hs:
            # Register to receive some bluetooth events
            hs.on_device_connected(self.device_connected)
            hs.on_incoming_call(self.incoming_call)
            hs.on_call_began(self.call_began)
            hs.on_call_ended(self.call_ended)

            hs.start('MyBluetoothHeadset', pincode='1234')
            hs.enable_pairability(timeout=30)

            self._hs = hs

            # Wait forever
            self.myMainLoop = GLib.MainLoop()
            self.myMainLoop.run()

    #
    # Call these from your event handlers
    #

    def voice_dial(self):
        self._hs.initiate_call()

    def dial_number(self, phone_number):
        if self._hs._hfp_audio_gateway:
            self._hs.dial(phone_number)

    def answer(self):
        if self._hs._hfp_audio_gateway and self._ringer:
            self._hs.answer_call()

    def hangup(self):
        if self._hs._hfp_audio_gateway:
            self._hs.hangup_call()

    def stop(self):
        self.myMainLoop.quit()


if __name__ == '__main__':
    # Enable debug logging to the console
    phony.base.log.send_to_stdout()

    #
    # Start the HFP service class, and never return.
    #
    # You can now pair your phone, and phony will setup
    # the necessary HFP profile services.
    #
    # To actually voice dial, dial a number or hangup a call,
    # you must call the voice_dial, dial_number, answer, or
    # hangup methods above from some kind of an asynchronous
    # event handler, like in response to some input on stdin,
    # or a button click, or a GPIO event, or maybe a command
    # sent over SPI or i2c.
    #
    service = ExampleHeadsetService()
    service.run()
