# KLayout batch renderer: klayout -zz -r render.py -rd gds=<in.gds> -rd lyp=<layers.lyp> -rd out=<out.png> [-rd w=1600 -rd h=1600]
# Uses the platform's own layer-properties file so layers get the PDK colours.
import pya

gds = globals().get("gds"); lyp = globals().get("lyp"); out = globals().get("out")
w = int(globals().get("w", 1600)); h = int(globals().get("h", 1600))
assert gds and out, "need -rd gds=... -rd out=..."

lv = pya.LayoutView()
lv.load_layout(gds, True)
if lyp:
    lv.load_layer_props(lyp)
lv.max_hier()                    # show all hierarchy levels
lv.set_config("background-color", "#ffffff")
lv.set_config("grid-visible", "false")
lv.zoom_fit()
lv.resize(w, h)
lv.save_image(out, w, h)
cv = lv.active_cellview()
bb = cv.layout().top_cell().dbbox()
print("render ok: %s top=%s bbox_um=%.1fx%.1f -> %s" % (gds, cv.layout().top_cell().name, bb.width(), bb.height(), out))
