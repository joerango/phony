from gi.repository import GLib
import phony.headset
import phony.base.ipc
import phony.base.log
import phony.audio.alsa
import phony.bluetooth.adapters
import phony.bluetooth.profiles.handsfree
import sys, os, termios, tty, signal

global service
global cmd_valid
global cmd
global phone_number
cmd_valid = False
cmd = None
phone_number = "123456"


def process_answer_call(signum, frame):
    # code for answering call
    global cmd_valid
    global cmd
    if signum == signal.SIGUSR1:
        print("Answering call")
        if not cmd_valid:
            cmd = "ANSWER!"
            cmd_valid = True
        else:
            print("Command not cleared")
    else:
        print(("Answering no call as I received an incorrect signal %d" % signum))


def process_dial_number(signum, frame):
    global cmd_valid
    global cmd
    if signum == signal.SIGUSR2:
        print("Dialing number")
        # service.print_statement(phone_number)
        if not cmd_valid:
            cmd = "DIAL!"
            cmd_valid = True
        else:
            print("Command not cleared")
    else:
        print(("Dialer received incorrect signal %d" % signum))


def process_handup(signum, frame):
    # code for answering call
    global cmd_valid
    global cmd
    if signum == signal.SIGUSR3:
        print("Hanging up")
        if not cmd_valid:
            cmd = "HANGUP!"
            cmd_valid = True
        else:
            print("Command not cleared")
    else:
        print(("Hangup received an incorrect signal %d" % signum))


def process_end(signum, frame):
    print("Child terminated normally")
    exit(0)


def tick():
    global service
    global cmd_valid
    global phone_number
    print("-tick-")
    if cmd_valid:
        if cmd == "DIAL!":
            try:
                service.dial_number(phone_number)
                print(("dialing ... %d" % int(phone_number)))
            except:
                print("dialing error")
        else:
            if cmd == "ANSWER!":
                try:
                    service.answer()
                    print("Now ansering ...")
                except:
                    print("ansering error")
        cmd_valid = False
    return True


class ExampleHeadsetService:
    _hs = None
    _call_in_progress = False
    phone_number = "123456"

    def device_connected(self):
        print('Device connected!')

    def incoming_call(self, call):
        print(('Incoming call: %s' % call))
        if self._call_in_progress:
            self._hs.deflect_call_to_voicemail()

    def call_began(self, call):
        print(('Call began: %s' % call))
        self._call_in_progress = True

    def call_ended(self, call):
        print(('Call ended: %s' % call))
        self._call_in_progress = False

    def print_statement(self, statement):
        print(statement)

    def run(self):
        """
        Starts phony service which manages device pairing and setting
        up of hands-free profile services.  This function never returns.
        """
        stdin_fd = sys.stdin.fileno()
        pid = os.fork()
        if not pid:
            # child
            os.setsid()
            bus = phony.base.ipc.BusProvider()
            # Find the first audio card that provides audio input and output mixers.
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

                signal.signal(signal.SIGTERM, process_end)
                signal.signal(signal.SIGINT, process_end)
                signal.signal(signal.SIGUSR1, process_answer_call)
                signal.signal(signal.SIGUSR2, process_dial_number)
                GLib.timeout_add_seconds(1, tick)
                loop = GLib.MainLoop()
                try:
                    loop.run()
                except KeyboardInterrupt:
                    print("Child caught keyborad interrupt")
                return 0
                # Wait forever> gobject.MainLoop().run()

        # parent
        def on_sigchld(signum, frame):
            assert signum == signal.SIGCHLD
            print("Child terminated - terminating parent")
            sys.exit(0)

        signal.signal(signal.SIGCHLD, on_sigchld)
        stdin_attrs = termios.tcgetattr(stdin_fd)
        tty.setcbreak(stdin_fd)
        while True:
            try:
                char = os.read(stdin_fd, 1)
                if char.lower() == "a":
                    os.kill(pid, signal.SIGUSR1)
                if char.lower() == "d":
                    os.kill(pid, signal.SIGUSR2)
            except KeyboardInterrupt:
                print("Forwarding SIGINT to child process")
                os.kill(pid, signal.SIGINT)
            except SystemExit:
                print("Caught SystemExit: cleaning up")
                termios.tcsetattr(stdin_fd, termios.TCSADRAIN, stdin_attrs)
                print("Parent terminated normally")
                return 0

    #
    # Call these from your event handlers
    #

    def voice_dial(self):
        self._hs.initiate_call()

    def dial_number(self, phone_number):
        self._hs.dial(phone_number)

    def answer(self):
        self._hs.answer_call()

    def hangup(self):
        self._hs.hangup()


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
