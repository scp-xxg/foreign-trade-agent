"""Optional: regenerate the committed SailAgent raster icons from the SVG master."""
from pathlib import Path
import io
import cairosvg
from PIL import Image
ROOT=Path(__file__).resolve().parents[2]
ASSETS=ROOT/'src/frontend/public/brand'
svg=(ASSETS/'sailagent-mark.svg').read_bytes()
for size,name in [(32,'sailagent-favicon.png'),(192,'sailagent-icon-192.png'),(512,'sailagent-icon-512.png')]:
    cairosvg.svg2png(bytestring=svg,write_to=str(ASSETS/name),output_width=size,output_height=size)
image=Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg,output_width=256,output_height=256)))
image.save(ASSETS/'sailagent.ico',sizes=[(16,16),(32,32),(48,48)])
word=(ASSETS/'sailagent-wordmark.svg').read_bytes()
cairosvg.svg2png(bytestring=word,write_to=str(ASSETS/'sailagent-wordmark.png'),output_width=1160,output_height=256)
print('SailAgent SVG master and PNG/ICO exports ready')

# White presentation preview; the reusable wordmark itself keeps transparency.
inner=(ASSETS/'sailagent-wordmark.svg').read_text().split('<title>SailAgent</title>',1)[1].rsplit('</svg>',1)[0]
preview='<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="360" viewBox="0 0 1000 360"><rect width="1000" height="360" rx="24" fill="white"/><g transform="translate(108,94) scale(2.7)">'+inner+'</g></svg>'
cairosvg.svg2png(bytestring=preview.encode(),write_to=str(ASSETS/'sailagent-preview.png'))
frames=[]
for i in range(12):
    t=i/11;x=14+37*t;y=45+12*t*(1-t)-1.5*t
    frame_svg=svg.decode().replace('cx="51" cy="43.5"',f'cx="{x}" cy="{y}"')
    png=cairosvg.svg2png(bytestring=frame_svg.encode(),output_width=48,output_height=48)
    frame=Image.open(io.BytesIO(png)).convert('RGBA')
    frames.append(frame)
frames[0].save(ROOT/'src/frontend/public/loader.gif',save_all=True,append_images=frames[1:],duration=80,loop=0,disposal=2)
done=svg.decode().replace('<rect width="64" height="64" rx="16" fill="#1264E8"/>','').replace('white','#94A3B8').replace('#70E5D0','#B0BFCE')
cairosvg.svg2png(bytestring=done.encode(),write_to=str(ROOT/'src/frontend/public/loader-done.png'),output_width=64,output_height=64)
