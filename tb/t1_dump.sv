// Extra simulation-only top (Icarus): dumps a VCD of the whole array when
// the plusarg +t1_vcd=<file> is given.  Used for demo/assets/t1_waveform.png.
module t1_dump;
  string vcd_file;
  initial begin
    if ($value$plusargs("t1_vcd=%s", vcd_file)) begin
      $dumpfile(vcd_file);
      $dumpvars(0, systolic_os);
    end
  end
endmodule
