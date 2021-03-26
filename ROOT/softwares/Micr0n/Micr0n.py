from .. import software_api
from cefpython3 import cefpython as cef
import ctypes

try:
	import tkinter as tk
except ImportError:
	import Tkinter as tk
import sys
import os
import platform
import logging as _logging
import requests

app_icon = "ACOS_Micron.png"
software_name = "Micr0n"
software_dir = "Micr0n"
is_GUI = True
min_size = (800, 440)
max_size = None
default_size = (900, 640)

# Fix for PyCharm hints warnings
WindowUtils = cef.WindowUtils()

# Platforms
WINDOWS = (platform.system() == "Windows")
LINUX = (platform.system() == "Linux")
MAC = (platform.system() == "Darwin")

# Globals
logger = _logging.getLogger("tkinter_.py")

# Constants
# Tk 8.5 doesn't support png images
IMAGE_EXT = ".png" if tk.TkVersion > 8.5 else ".gif"

def on_app_launch(frame:tk.Frame, width:int=900, height:int=640):
	# Testing if connection
	if software_api.test_connection() is True:
		if "no_connection_title" in globals():
			globals()["no_connection_title"].pack_forget()
			globals()["no_connection_title"].destroy()
			globals()["no_connection_subtitle"].pack_forget()
			globals()["no_connection_subtitle"].destroy()

		logger.setLevel(_logging.CRITICAL)
		stream_handler = _logging.StreamHandler()
		formatter = _logging.Formatter("[%(filename)s] %(message)s")
		stream_handler.setFormatter(formatter)
		logger.addHandler(stream_handler)
		logger.info("CEF Python {ver}".format(ver=cef.__version__))
		logger.info("Python {ver} {arch}".format(
			ver=platform.python_version(), arch=platform.architecture()[0]))
		logger.info("Tk {ver}".format(ver=tk.Tcl().eval('info patchlevel')))
		assert cef.__version__ >= "55.3", "CEF Python v55.3+ required to run this"
		sys.excepthook = cef.ExceptHook  # To shutdown all CEF processes on error
		# Tk must be initialized before CEF otherwise fatal error (Issue #306)
		app = MainFrame(frame)
		settings = {}
		if MAC:
			settings["external_message_pump"] = True
		cef.Initialize(settings=settings)
	else:
		if not "no_connection_title" in globals():
			globals()["no_connection_title"] = tk.Label(
				frame,
				text = "Oh No !",
				font = ("Impact", 22)
			)
			globals()["no_connection_title"].pack()
			globals()["no_connection_subtitle"] = tk.Label(
				frame,
				text = "Sounds like no connection is available...",
				font = ("Impact", 14)
			)
			globals()["no_connection_subtitle"].pack()
		# Testing again
		frame.after(5000, on_app_launch, frame, width, height)

class MainFrame(tk.Frame):
	def __init__(self, frame):
		self.browser_frame = None
		self.navigation_bar = None
		self.frame = frame

		# Root
		tk.Grid.rowconfigure(frame, 0, weight=1)
		tk.Grid.columnconfigure(frame, 0, weight=1)

		# MainFrame
		tk.Frame.__init__(self, frame)
		self.master.bind("<Configure>", self.on_frame_configure)
		self.setup_icon()
		self.bind("<Configure>", self.on_configure)
		self.bind("<FocusIn>", self.on_focus_in)
		self.bind("<FocusOut>", self.on_focus_out)

		# NavigationBar
		self.navigation_bar = NavigationBar(self)
		self.navigation_bar.grid(row=0, column=0,
		                         sticky=(tk.N + tk.S + tk.E + tk.W))
		tk.Grid.rowconfigure(self, 0, weight=0)
		tk.Grid.columnconfigure(self, 0, weight=0)

		# BrowserFrame
		self.browser_frame = BrowserFrame(self, self.navigation_bar)
		self.browser_frame.grid(row=1, column=0,
		                        sticky=(tk.N + tk.S + tk.E + tk.W))
		tk.Grid.rowconfigure(self, 1, weight=1)
		tk.Grid.columnconfigure(self, 0, weight=1)

		# Pack MainFrame
		self.pack(fill=tk.BOTH, expand=tk.YES)

	def on_frame_configure(self, _):
		logger.debug("MainFrame.on_frame_configure")
		if self.browser_frame:
			self.browser_frame.on_frame_configure()

	def on_configure(self, event):
		logger.debug("MainFrame.on_configure")
		if self.browser_frame:
			width = event.width
			height = event.height
			if self.navigation_bar:
				height = height - self.navigation_bar.winfo_height()
			self.browser_frame.on_mainframe_configure(width, height)

	def on_focus_in(self, _):
		logger.debug("MainFrame.on_focus_in")

	def on_focus_out(self, _):
		logger.debug("MainFrame.on_focus_out")

	def get_browser(self):
		if self.browser_frame:
			return self.browser_frame.browser
		return None

	def get_browser_frame(self):
		if self.browser_frame:
			return self.browser_frame
		return None

	def setup_icon(self):
		resources = os.path.join(os.path.dirname(__file__), "resources")
		icon_path = os.path.join(resources, "tkinter" + IMAGE_EXT)
		if os.path.exists(icon_path):
			self.icon = tk.PhotoImage(file=icon_path)
			# noinspection PyProtectedMember
			self.master.call("wm", "iconphoto", self.master._w, self.icon)

class BrowserFrame(tk.Frame):

	def __init__(self, mainframe, navigation_bar=None):
		self.navigation_bar = navigation_bar
		self.closing = False
		self.browser = None
		tk.Frame.__init__(self, mainframe)
		self.mainframe = mainframe
		self.bind("<FocusIn>", self.on_focus_in)
		self.bind("<FocusOut>", self.on_focus_out)
		self.bind("<Configure>", self.on_configure)
		"""For focus problems see Issue #255 and Issue #535. """
		self.focus_set()

	def embed_browser(self):
		window_info = cef.WindowInfo()
		rect = [0, 0, self.winfo_width(), self.winfo_height()]
		window_info.SetAsChild(self.get_window_handle(), rect)
		self.browser = cef.CreateBrowserSync(window_info,
		                                     url="https://www.google.com/")
		assert self.browser
		self.browser.SetClientHandler(LifespanHandler(self))
		self.browser.SetClientHandler(LoadHandler(self))
		self.browser.SetClientHandler(FocusHandler(self))
		self.message_loop_work()

	def get_window_handle(self):
		if MAC:
			# Do not use self.winfo_id() on Mac, because of these issues:
			# 1. Window id sometimes has an invalid negative value (Issue #308).
			# 2. Even with valid window id it crashes during the call to NSView.setAutoresizingMask:
			#    https://github.com/cztomczak/cefpython/issues/309#issuecomment-661094466
			#
			# To fix it using PyObjC package to obtain window handle. If you change structure of windows then you
			# need to do modifications here as well.
			#
			# There is still one issue with this solution. Sometimes there is more than one window, for example when application
			# didn't close cleanly last time Python displays an NSAlert window asking whether to Reopen that window. In such
			# case app will crash and you will see in console:
			# > Fatal Python error: PyEval_RestoreThread: NULL tstate
			# > zsh: abort      python tkinter_.py
			# Error messages related to this: https://github.com/cztomczak/cefpython/issues/441
			#
			# There is yet another issue that might be related as well:
			# https://github.com/cztomczak/cefpython/issues/583

			# noinspection PyUnresolvedReferences
			from AppKit import NSApp
			# noinspection PyUnresolvedReferences
			import objc
			logger.info("winfo_id={}".format(self.winfo_id()))
			# noinspection PyUnresolvedReferences
			content_view = objc.pyobjc_id(NSApp.windows()[-1].contentView())
			logger.info("content_view={}".format(content_view))
			return content_view
		elif self.winfo_id() > 0:
			return self.winfo_id()
		else:
			raise Exception("Couldn't obtain window handle")

	def message_loop_work(self):
		cef.MessageLoopWork()
		self.after(10, self.message_loop_work)

	def on_configure(self, _):
		if not self.browser:
			self.embed_browser()

	def on_frame_configure(self):
		# Root <Configure> event will be called when top window is moved
		if self.browser:
			self.browser.NotifyMoveOrResizeStarted()

	def on_mainframe_configure(self, width, height):
		if self.browser:
			if WINDOWS:
				ctypes.windll.user32.SetWindowPos(
					self.browser.GetWindowHandle(), 0,
					0, 0, width, height, 0x0002)
			elif LINUX:
				self.browser.SetBounds(0, 0, width, height)
			self.browser.NotifyMoveOrResizeStarted()

	def on_focus_in(self, _):
		logger.debug("BrowserFrame.on_focus_in")
		if self.browser:
			self.browser.SetFocus(True)

	def on_focus_out(self, _):
		logger.debug("BrowserFrame.on_focus_out")
		"""For focus problems see Issue #255 and Issue #535. """
		if LINUX and self.browser:
			self.browser.SetFocus(False)

	def on_frame_close(self):
		logger.info("BrowserFrame.on_frame_close")
		if self.browser:
			logger.debug("CloseBrowser")
			self.browser.CloseBrowser(True)
			self.clear_browser_references()
			cef.Shutdown()

	def clear_browser_references(self):
		# Clear browser references that you keep anywhere in your
		# code. All references must be cleared for CEF to shutdown cleanly.
		self.browser = None

class LifespanHandler(object):

	def __init__(self, tkFrame):
		self.tkFrame = tkFrame

	def OnBeforeClose(self, browser, **_):
		logger.debug("LifespanHandler.OnBeforeClose")
		#self.tkFrame.quit()

class LoadHandler(object):

	def __init__(self, browser_frame):
		self.browser_frame = browser_frame

	def OnLoadStart(self, browser, **_):
		if self.browser_frame.master.navigation_bar:
			self.browser_frame.master.navigation_bar.set_url(browser.GetUrl())

class FocusHandler(object):
	"""For focus problems see Issue #255 and Issue #535. """

	def __init__(self, browser_frame):
		self.browser_frame = browser_frame

	def OnTakeFocus(self, next_component, **_):
		logger.debug("FocusHandler.OnTakeFocus, next={next}"
		             .format(next=next_component))

	def OnSetFocus(self, source, **_):
		logger.debug("FocusHandler.OnSetFocus, source={source}"
		             .format(source=source))
		if LINUX:
			return False
		else:
			return True

	def OnGotFocus(self, **_):
		logger.debug("FocusHandler.OnGotFocus")
		if LINUX:
			self.browser_frame.focus_set()

class NavigationBar(tk.Frame):

	def __init__(self, master):
		self.back_state = tk.NONE
		self.forward_state = tk.NONE
		self.back_image = None
		self.forward_image = None
		self.reload_image = None

		tk.Frame.__init__(self, master)
		resources = os.path.join(os.path.dirname(__file__), "resources")

		# Back button
		back_png = os.path.join(resources, "back" + IMAGE_EXT)
		self.back_button = tk.Button(self, text="<-",
		                             command=self.go_back)
		self.back_button.grid(row=0, column=0)

		# Forward button
		forward_png = os.path.join(resources, "forward" + IMAGE_EXT)
		self.forward_button = tk.Button(self, text="->",
		                                command=self.go_forward)
		self.forward_button.grid(row=0, column=1)

		# Reload button
		reload_png = os.path.join(resources, "reload" + IMAGE_EXT)
		self.reload_button = tk.Button(self, text="REFRESH",
		                               command=self.reload)
		self.reload_button.grid(row=0, column=2)

		# Url entry
		self.url_entry = tk.Entry(self)
		self.url_entry.bind("<FocusIn>", self.on_url_focus_in)
		self.url_entry.bind("<FocusOut>", self.on_url_focus_out)
		self.url_entry.bind("<Return>", self.on_load_url)
		self.url_entry.bind("<Button-1>", self.on_button1)
		self.url_entry.grid(row=0, column=3,
		                    sticky=(tk.N + tk.S + tk.E + tk.W))
		tk.Grid.rowconfigure(self, 0, weight=100)
		tk.Grid.columnconfigure(self, 3, weight=100)

		# Update state of buttons
		self.update_state()

	def go_back(self):
		if self.master.get_browser():
			self.master.get_browser().GoBack()

	def go_forward(self):
		if self.master.get_browser():
			self.master.get_browser().GoForward()

	def reload(self):
		if self.master.get_browser():
			self.master.get_browser().Reload()

	def set_url(self, url):
		self.url_entry.delete(0, tk.END)
		self.url_entry.insert(0, url)

	def on_url_focus_in(self, _):
		logger.debug("NavigationBar.on_url_focus_in")

	def on_url_focus_out(self, _):
		logger.debug("NavigationBar.on_url_focus_out")

	def on_load_url(self, _):
		if self.master.get_browser():
			self.master.get_browser().StopLoad()
			self.master.get_browser().LoadUrl(self.url_entry.get())

	def on_button1(self, _):
		"""For focus problems see Issue #255 and Issue #535. """
		logger.debug("NavigationBar.on_button1")
		self.master.master.focus_force()

	def update_state(self):
		browser = self.master.get_browser()
		if not browser:
			if self.back_state != tk.DISABLED:
				self.back_button.config(state=tk.DISABLED)
				self.back_state = tk.DISABLED
			if self.forward_state != tk.DISABLED:
				self.forward_button.config(state=tk.DISABLED)
				self.forward_state = tk.DISABLED
			self.after(100, self.update_state)
			return
		if browser.CanGoBack():
			if self.back_state != tk.NORMAL:
				self.back_button.config(state=tk.NORMAL)
				self.back_state = tk.NORMAL
		else:
			if self.back_state != tk.DISABLED:
				self.back_button.config(state=tk.DISABLED)
				self.back_state = tk.DISABLED
		if browser.CanGoForward():
			if self.forward_state != tk.NORMAL:
				self.forward_button.config(state=tk.NORMAL)
				self.forward_state = tk.NORMAL
		else:
			if self.forward_state != tk.DISABLED:
				self.forward_button.config(state=tk.DISABLED)
				self.forward_state = tk.DISABLED
		self.after(100, self.update_state)
