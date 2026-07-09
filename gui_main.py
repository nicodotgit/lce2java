import sys
import subprocess
import os
import json
import signal
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QTabWidget,
    QMessageBox, QDialog, QProgressBar, QGroupBox
)
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtCore import Qt
import zlib
import multiprocessing

from gui_worker import ConversionWorker
from gui_dialogs import (
    lce2jePlayerMappingDialog,
    CancelDialog
)

class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About lce2je")
        self.resize(450, 350)
        
        layout = QVBoxLayout(self)
        
        # Logo
        logo_label = QLabel()
        logo_path = os.path.join(os.path.dirname(__file__), "assets", "logo", "lce2je_logo_128x128.png")
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            logo_label.setPixmap(pixmap)
            logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo_label)
        
        info_label = QLabel(
            "<h2>lce2je</h2>"
            "<p><b>Version 1.0.0</b></p>"
            "<p>A Minecraft Legacy Console Edition (Windows64) to Java 1.6.4 Converter.</p>"
            "<p>Created with ♥ for archiving and exploring old worlds.</p>"
            "<p><b>GitHub:</b> <a href='https://github.com/nicodotgit/lce2je'>https://github.com/nicodotgit/lce2je</a></p>"
            "<p><small>&copy; 2026 nicodotgit. Licensed under the GNU GPLv3.</small></p>"
        )
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setOpenExternalLinks(True)
        layout.addWidget(info_label)
        
        btn = QPushButton("Close")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle("lce2je")
        self.resize(700, 500)
        
        icon_path = os.path.join(os.path.dirname(__file__), "assets", "logo", "lce2je_logo.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            
        self.lce2je_in_path = ""
        self.lce2je_out_path = ""
        
        self.init_ui()
        self.worker = None

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        self.init_lce2je_layout(main_layout)
        
        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_convert = QPushButton("Convert")
        self.btn_convert.setEnabled(False)  # Disabled by default
        self.btn_convert.clicked.connect(self.start_conversion)
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.cancel_clicked)
        
        btn_layout.addWidget(self.btn_convert)
        btn_layout.addWidget(self.btn_cancel)
        main_layout.addLayout(btn_layout)
        
        # Progress Checklist
        self.steps_group = QGroupBox("Conversion Progress")
        self.steps_layout = QVBoxLayout()
        self.steps_group.setLayout(self.steps_layout)
        self.steps_group.setVisible(False)
        main_layout.addWidget(self.steps_group)
        
        self.current_step_label = None
        self.current_progress_bar = None
        
        # Menu
        menu = self.menuBar()
        about_action = menu.addAction("About")
        about_action.triggered.connect(self.show_about)

    def init_lce2je_layout(self, main_layout):
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        # Input MS
        self.btn_lce2je_in = QPushButton("Select .ms world")
        self.btn_lce2je_in.setMinimumHeight(40)
        self.btn_lce2je_in.clicked.connect(self.select_lce2je_in)
        layout.addWidget(self.btn_lce2je_in)
        
        self.lbl_lce2je_in_status = QLabel("")
        self.lbl_lce2je_in_status.setWordWrap(True)
        layout.addWidget(self.lbl_lce2je_in_status)
        
        # Output Dir
        self.btn_lce2je_out = QPushButton("Select Output Directory")
        self.btn_lce2je_out.setMinimumHeight(40)
        self.btn_lce2je_out.clicked.connect(self.select_lce2je_out)
        layout.addWidget(self.btn_lce2je_out)
        
        self.lbl_lce2je_out_status = QLabel("")
        self.lbl_lce2je_out_status.setWordWrap(True)
        layout.addWidget(self.lbl_lce2je_out_status)
        
        layout.addStretch()
        main_layout.addLayout(layout)

    def update_convert_button_state(self):
        valid = bool(self.lce2je_in_path and self.lce2je_out_path)
        self.btn_convert.setEnabled(valid)
        
    def check_progress_compatibility(self, in_path, out_path):
        if not in_path or not out_path: return True, ""
        prog_file = os.path.join(out_path, "lce2je_progress.json")
        if os.path.exists(prog_file):
            try:
                with open(prog_file, "r") as f:
                    state = json.load(f)
                saved_in = state.get("input_file")
                if saved_in and os.path.abspath(saved_in) != os.path.abspath(in_path):
                    return False, "Directory contains progress for a different world."
            except Exception:
                pass
        return True, ""

    def get_native_open_file(self, title, filter_ext):
        if sys.platform.startswith("linux"):
            desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
            if "kde" in desktop:
                try:
                    res = subprocess.run(["kdialog", "--getopenfilename", ".", f"*{filter_ext}"], capture_output=True, text=True)
                    if res.returncode == 0: return res.stdout.strip()
                except FileNotFoundError: pass
            try:
                res = subprocess.run(["zenity", "--file-selection", "--title", title, f"--file-filter={filter_ext}"], capture_output=True, text=True)
                if res.returncode == 0: return res.stdout.strip()
            except FileNotFoundError: pass
        
        path, _ = QFileDialog.getOpenFileName(self, title, "", f"Minecraft Save (*{filter_ext})")
        return path

    def get_native_directory(self, title):
        if sys.platform.startswith("linux"):
            desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
            if "kde" in desktop:
                try:
                    res = subprocess.run(["kdialog", "--getexistingdirectory", "."], capture_output=True, text=True)
                    if res.returncode == 0: return res.stdout.strip()
                except FileNotFoundError: pass
            try:
                res = subprocess.run(["zenity", "--file-selection", "--directory", "--title", title], capture_output=True, text=True)
                if res.returncode == 0: return res.stdout.strip()
            except FileNotFoundError: pass
            
        return QFileDialog.getExistingDirectory(self, title)

    def select_lce2je_in(self):
        path = self.get_native_open_file("Select saveData.ms", ".ms")
        if path:
            if not path.endswith('.ms'):
                self.lbl_lce2je_in_status.setText("❌ Invalid file. Must end with .ms")
                self.lbl_lce2je_in_status.setStyleSheet("color: red;")
                self.lce2je_in_path = ""
            else:
                valid, msg = self.validate_ms_file(path)
                if not valid:
                    self.lbl_lce2je_in_status.setText(f"❌ Invalid file: {msg}")
                    self.lbl_lce2je_in_status.setStyleSheet("color: red;")
                    self.lce2je_in_path = ""
                else:
                    if self.lce2je_out_path:
                        if os.path.exists(os.path.join(self.lce2je_out_path, "level.dat")):
                            self.lbl_lce2je_in_status.setText("❌ Output directory is already a completely converted world.")
                            self.lbl_lce2je_in_status.setStyleSheet("color: red;")
                            self.lce2je_in_path = ""
                            self.update_convert_button_state()
                            return
                        compat, cmsg = self.check_progress_compatibility(path, self.lce2je_out_path)
                        if not compat:
                            self.lbl_lce2je_in_status.setText(f"❌ {cmsg}")
                            self.lbl_lce2je_in_status.setStyleSheet("color: red;")
                            self.lce2je_in_path = ""
                            self.update_convert_button_state()
                            return
                            
                    self.lbl_lce2je_in_status.setText(f"✅ Selected: {os.path.basename(path)}")
                    self.lbl_lce2je_in_status.setStyleSheet("color: green;")
                    self.lce2je_in_path = path
                    
                    if self.lce2je_out_path:
                        compat, cmsg = self.check_progress_compatibility(path, self.lce2je_out_path)
                        if compat and self.lbl_lce2je_out_status.text().startswith("❌"):
                            self.lbl_lce2je_out_status.setText(f"✅ Selected: {os.path.basename(self.lce2je_out_path)}")
                            self.lbl_lce2je_out_status.setStyleSheet("color: green;")
        self.update_convert_button_state()
        
    def select_lce2je_out(self):
        path = self.get_native_directory("Select Output Directory")
        if path:
            if os.path.exists(os.path.join(path, "level.dat")):
                self.lbl_lce2je_out_status.setText("❌ Directory already contains a completely converted world (level.dat exists).")
                self.lbl_lce2je_out_status.setStyleSheet("color: red;")
                self.lce2je_out_path = ""
            else:
                if self.lce2je_in_path:
                    compat, cmsg = self.check_progress_compatibility(self.lce2je_in_path, path)
                    if not compat:
                        self.lbl_lce2je_out_status.setText(f"❌ {cmsg}")
                        self.lbl_lce2je_out_status.setStyleSheet("color: red;")
                        self.lce2je_out_path = ""
                        self.update_convert_button_state()
                        return
                
                self.lbl_lce2je_out_status.setText(f"✅ Selected: {os.path.basename(path) or path}")
                self.lbl_lce2je_out_status.setStyleSheet("color: green;")
                self.lce2je_out_path = path
        self.update_convert_button_state()

    def validate_ms_file(self, path):
        if not os.path.exists(path): return False, "File does not exist."
        try:
            with open(path, 'rb') as f:
                f.read(8) # Read the 8 bytes wrapper
                data = f.read(1024 * 1024) # Read 1MB chunk to test
                if not data: return False, "File is empty."
                try:
                    # Try decompressing the first chunk to verify structure
                    zobj = zlib.decompressobj()
                    zobj.decompress(data)
                    return True, ""
                except zlib.error as e:
                    return False, f"ZLIB archive corrupted: {e}"
        except Exception as e:
            return False, f"Could not read file: {e}"
            
    def show_about(self):
        dlg = AboutDialog(self)
        dlg.exec()

    def log(self, msg):
        if msg.startswith("--- Step"):
            step_text = msg.replace("---", "").strip()
            
            # Mark previous step as completed
            if self.current_step_label:
                old_text = self.current_step_label.text()[2:] # Remove the hourglass emoji
                self.current_step_label.setText(f"✅ {old_text}")
                if self.current_progress_bar:
                    self.current_progress_bar.setVisible(False)
            
            # Create new step
            self.current_step_label = QLabel(f"⏳ {step_text}")
            self.current_progress_bar = QProgressBar()
            self.current_progress_bar.setRange(0, 0) # Indeterminate initially
            
            self.steps_layout.addWidget(self.current_step_label)
            self.steps_layout.addWidget(self.current_progress_bar)
            
        elif msg.startswith("WARNING") or msg.startswith("Error"):
            lbl = QLabel(msg)
            lbl.setWordWrap(True)
            if msg.startswith("Error"):
                lbl.setStyleSheet("color: red; font-weight: bold;")
            else:
                lbl.setStyleSheet("color: orange;")
            self.steps_layout.addWidget(lbl)

    def cancel_clicked(self):
        dlg = CancelDialog(self)
        dlg.exec()
        action = dlg.get_action()
        if action in ["s", "n"]:
            if self.worker:
                # Terminate multiprocessing workers first
                for p in multiprocessing.active_children():
                    p.terminate()
                    
                # Restore sys streams safely BEFORE killing the thread
                if hasattr(self.worker, 'redirector') and self.worker.redirector:
                    sys.stdout = self.worker.redirector.original_stream
                if hasattr(self.worker, 'err_redirector') and self.worker.err_redirector:
                    sys.stderr = self.worker.err_redirector.original_stream
                    
                # Forcefully terminate the QThread without waiting
                self.worker.terminate()
                
                # Perform cleanup safely after the thread is killed
                if action == "s" and hasattr(self.worker, 'progress_mgr'):
                    self.worker.progress_mgr.cleanup_temp_files(self.worker.temp_dir)
                elif action == "n" and hasattr(self.worker, 'progress_mgr'):
                    self.worker.progress_mgr.nuke_progress(self.worker.temp_dir)
                
            # Reset UI
            self.lce2je_in_path = ""
            self.lce2je_out_path = ""
            
            if hasattr(self, 'lbl_lce2je_in_status'):
                self.lbl_lce2je_in_status.setText("")
                self.lbl_lce2je_out_status.setText("")
            
            self.steps_group.setVisible(False)
            self.update_convert_button_state()
            self.btn_cancel.setEnabled(False)

    def start_conversion(self):
        in_path = self.lce2je_in_path
        out_path = self.lce2je_out_path
        mode = "lce2je"
            
        if not in_path or not out_path:
            QMessageBox.warning(self, "Error", "Please make sure both input and output are valid.")
            return
            
        self.btn_convert.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        
        # Clear previous steps
        while self.steps_layout.count():
            child = self.steps_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
                
        self.current_step_label = None
        self.current_progress_bar = None
        self.steps_group.setVisible(True)
        
        self.worker = ConversionWorker(mode, in_path, out_path)
        
        # Connect base signals
        self.worker.log_msg.connect(self.log)
        self.worker.error_msg.connect(self.on_error)
        self.worker.finished_success.connect(self.on_success)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.chunk_progress.connect(self.on_chunk_progress)
        
        # Connect dialog signals
        self.worker.ask_lce_player_mapping.connect(self.handle_lce_player_mapping)
        
        self.worker.start()

    def on_error(self, msg):
        if self.current_step_label:
            old_text = self.current_step_label.text()[2:]
            self.current_step_label.setText(f"❌ {old_text}")
            if self.current_progress_bar:
                self.current_progress_bar.setVisible(False)
        
        lbl = QLabel(f"❌ Error: {msg}")
        lbl.setStyleSheet("color: red; font-weight: bold;")
        lbl.setWordWrap(True)
        self.steps_layout.addWidget(lbl)
        
        QMessageBox.critical(self, "Error", msg)
        
    def on_success(self, path):
        if self.current_step_label:
            old_text = self.current_step_label.text()[2:]
            self.current_step_label.setText(f"✅ {old_text}")
            if self.current_progress_bar:
                self.current_progress_bar.setVisible(False)
                
        lbl = QLabel("✅ Conversion completed successfully!")
        lbl.setStyleSheet("color: green; font-weight: bold;")
        self.steps_layout.addWidget(lbl)
        
        self.btn_convert.setText("Open Output Directory")
        try: self.btn_convert.clicked.disconnect()
        except TypeError: pass
        self.btn_convert.clicked.connect(self.open_output_dir)
        self.btn_convert.setEnabled(True)
        
        self.btn_cancel.setText("Clear")
        try: self.btn_cancel.clicked.disconnect()
        except TypeError: pass
        self.btn_cancel.clicked.connect(self.clear_gui)
        self.btn_cancel.setEnabled(True)
        
        self.btn_lce2je_in.setEnabled(False)
        self.btn_lce2je_out.setEnabled(False)

    def clear_gui(self):
        self.btn_convert.setText("Convert")
        try: self.btn_convert.clicked.disconnect()
        except TypeError: pass
        self.btn_convert.clicked.connect(self.start_conversion)
        
        self.btn_cancel.setText("Cancel")
        try: self.btn_cancel.clicked.disconnect()
        except TypeError: pass
        self.btn_cancel.clicked.connect(self.cancel_clicked)
        
        self.btn_lce2je_in.setEnabled(True)
        self.btn_lce2je_out.setEnabled(True)
        
        self.lce2je_in_path = ""
        self.lce2je_out_path = ""
        
        if hasattr(self, 'lbl_lce2je_in_status'):
            self.lbl_lce2je_in_status.setText("")
            self.lbl_lce2je_out_status.setText("")
            
        # Clean steps layout
        while self.steps_layout.count():
            child = self.steps_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
                
        self.steps_group.setVisible(False)
        self.update_convert_button_state()
        self.btn_cancel.setEnabled(False)

    def open_output_dir(self):
        if not self.lce2je_out_path or not os.path.exists(self.lce2je_out_path): return
        try:
            if sys.platform == "win32":
                os.startfile(self.lce2je_out_path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", self.lce2je_out_path])
            else:
                subprocess.Popen(["xdg-open", self.lce2je_out_path])
        except Exception as e:
            print(f"Could not automatically open folder: {e}")
            
    def on_chunk_progress(self, curr, total):
        if self.current_step_label:
            self.current_step_label.setText(f"⏳ Converting Regions ({curr}/{total})")
        if self.current_progress_bar:
            if self.current_progress_bar.maximum() == 0:
                self.current_progress_bar.setRange(0, total)
            self.current_progress_bar.setValue(curr)
        
    def on_worker_finished(self):
        # Only reset the button states if we are not in the "Success" state
        if self.btn_cancel.text() != "Clear":
            self.update_convert_button_state()
            self.btn_cancel.setEnabled(False)

    def handle_lce_player_mapping(self, players):
        dlg = lce2jePlayerMappingDialog(players, self)
        dlg.exec()
        kept, host = dlg.get_selections()
        self.worker.on_lce_player_mapping_resolved(kept, host)



if __name__ == '__main__':
    multiprocessing.freeze_support()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
