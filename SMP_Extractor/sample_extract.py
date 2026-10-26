import wx
import wave
import array
import os
import struct

class SMPBatchConverterFrame(wx.Frame):
    def __init__(self):
        super().__init__(parent=None, title='SP-404 MKII Batch SMP Converter', size=(600, 450))
        
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        # --- Section 1: Source Folder ---
        sb_src = wx.StaticBox(panel, label="1. Source")
        sbs_src = wx.StaticBoxSizer(sb_src, wx.VERTICAL)
        
        hbox_src = wx.BoxSizer(wx.HORIZONTAL)
        hbox_src.Add(wx.StaticText(panel, label="Folder containing .SMP files:"), flag=wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, border=5)
        self.dir_picker_src = wx.DirPickerCtrl(panel, message="Select Source Folder",
                                               style=wx.DIRP_USE_TEXTCTRL | wx.DIRP_DIR_MUST_EXIST)
        hbox_src.Add(self.dir_picker_src, proportion=1, flag=wx.EXPAND)
        sbs_src.Add(hbox_src, flag=wx.EXPAND|wx.ALL, border=5)
        vbox.Add(sbs_src, flag=wx.EXPAND|wx.ALL, border=10)

        # --- Section 2: Destination Folder ---
        sb_dst = wx.StaticBox(panel, label="2. Destination")
        sbs_dst = wx.StaticBoxSizer(sb_dst, wx.VERTICAL)
        
        # Toggle Checkbox
        self.chk_custom_dest = wx.CheckBox(panel, label="Save to a different folder?")
        self.chk_custom_dest.Bind(wx.EVT_CHECKBOX, self.on_toggle_dest)
        sbs_dst.Add(self.chk_custom_dest, flag=wx.ALL, border=5)
        
        # Destination Picker (Initially Disabled)
        hbox_dst = wx.BoxSizer(wx.HORIZONTAL)
        hbox_dst.Add(wx.StaticText(panel, label="Output Folder:"), flag=wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, border=5)
        self.dir_picker_dst = wx.DirPickerCtrl(panel, message="Select Destination Folder",
                                               style=wx.DIRP_USE_TEXTCTRL | wx.DIRP_DIR_MUST_EXIST)
        self.dir_picker_dst.Enable(False) # Disabled by default
        hbox_dst.Add(self.dir_picker_dst, proportion=1, flag=wx.EXPAND)
        
        sbs_dst.Add(hbox_dst, flag=wx.EXPAND|wx.ALL, border=5)
        vbox.Add(sbs_dst, flag=wx.EXPAND|wx.ALL, border=10)

        # --- Section 3: Action ---
        self.btn_convert = wx.Button(panel, label='Check Files & Convert Batch')
        self.btn_convert.Bind(wx.EVT_BUTTON, self.on_start_process)
        vbox.Add(self.btn_convert, flag=wx.ALIGN_CENTER|wx.ALL, border=10)

        # --- Section 4: Feedback ---
        self.gauge = wx.Gauge(panel, range=100, size=(250, 25))
        vbox.Add(self.gauge, flag=wx.EXPAND|wx.LEFT|wx.RIGHT, border=20)
        
        self.log = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY)
        vbox.Add(self.log, proportion=1, flag=wx.EXPAND | wx.ALL, border=10)
        
        panel.SetSizer(vbox)
        self.Centre()
        self.Show()

    def on_toggle_dest(self, event):
        # Enable/Disable the destination picker based on checkbox
        is_checked = self.chk_custom_dest.GetValue()
        self.dir_picker_dst.Enable(is_checked)

    def on_start_process(self, event):
        self.log.Clear()
        source_dir = self.dir_picker_src.GetPath()
        
        # Validation: Source
        if not source_dir or not os.path.exists(source_dir):
            self.log.AppendText("Error: Invalid source directory.\n")
            return

        # Validation: Destination
        if self.chk_custom_dest.GetValue():
            dest_dir = self.dir_picker_dst.GetPath()
            if not dest_dir or not os.path.exists(dest_dir):
                self.log.AppendText("Error: Invalid destination directory.\n")
                return
        else:
            dest_dir = source_dir

        # Find all .SMP files
        smp_files = [f for f in os.listdir(source_dir) if f.lower().endswith('.smp')]
        
        if not smp_files:
            self.log.AppendText("No .SMP files found in source directory.\n")
            return

        self.log.AppendText(f"Found {len(smp_files)} .SMP files.\nChecking for existing WAV files...\n")

        # --- PRE-CHECK FOR OVERWRITES ---
        files_to_process = []
        conflicts = []

        for f in smp_files:
            input_path = os.path.join(source_dir, f)
            filename_no_ext = os.path.splitext(f)[0]
            output_filename = filename_no_ext + ".wav"
            output_path = os.path.join(dest_dir, output_filename)
            
            # Store tuple for processing later
            files_to_process.append((input_path, output_path))
            
            if os.path.exists(output_path):
                conflicts.append(output_filename)

        # If conflicts exist, ASK USER
        if conflicts:
            msg = (f"Warning: {len(conflicts)} files already exist in the destination folder.\n"
                   f"Examples: {', '.join(conflicts[:3])}...\n\n"
                   "Do you want to overwrite these files?")
            
            dlg = wx.MessageDialog(self, msg, "Confirm Overwrite", wx.YES_NO | wx.ICON_WARNING)
            result = dlg.ShowModal()
            dlg.Destroy()

            if result == wx.ID_NO:
                self.log.AppendText("Process Cancelled by user to prevent overwrite.\n")
                return
            else:
                self.log.AppendText("User authorized overwrite. Proceeding...\n")
        
        # --- EXECUTE CONVERSION ---
        self.gauge.SetRange(len(files_to_process))
        self.gauge.SetValue(0)
        
        success_count = 0
        
        for index, (in_path, out_path) in enumerate(files_to_process):
            try:
                self.convert_smp(in_path, out_path)
                self.log.AppendText(f"Converted: {os.path.basename(in_path)} -> {os.path.basename(out_path)}\n")
                success_count += 1
            except Exception as e:
                self.log.AppendText(f"Failed: {os.path.basename(in_path)} | Error: {str(e)}\n")
            
            # Update UI
            self.gauge.SetValue(index + 1)
            wx.GetApp().Yield() # Keep GUI responsive
            
        self.log.AppendText(f"\nBatch Complete. {success_count}/{len(files_to_process)} converted successfully.\n")
        wx.MessageBox("Batch Conversion Complete!", "Done", wx.OK | wx.ICON_INFORMATION)

    def convert_smp(self, input_file, output_file):
        # Configuration: 48kHz, 16-bit, Stereo, Big Endian Input
        CHANNELS = 2
        SAMPLE_WIDTH = 2
        FRAME_RATE = 48000
        HEADER_SKIP_SAMPLES = 200 
        header_bytes_to_skip = HEADER_SKIP_SAMPLES * CHANNELS * SAMPLE_WIDTH

        with open(input_file, 'rb') as smp:
            smp.seek(header_bytes_to_skip)
            raw_data = smp.read()

        audio_array = array.array('h')
        audio_array.frombytes(raw_data)
        audio_array.byteswap() # Big Endian -> Little Endian
        
        with wave.open(output_file, 'wb') as wav:
            wav.setnchannels(CHANNELS)
            wav.setsampwidth(SAMPLE_WIDTH)
            wav.setframerate(FRAME_RATE)
            wav.writeframes(audio_array.tobytes())

if __name__ == '__main__':
    app = wx.App()
    frame = SMPBatchConverterFrame()
    app.MainLoop()