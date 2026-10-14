"""Execute pinned C++ partial refresh(true); compare restored scan/activation trace."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.reference_oracle import BASE
from hink_diag.panel import Panel
from hink_diag.config import Config
from hink_diag.transport import mock_transport,Budget,FakeClock

MAIN=r'''
#define private public
#include "epd/GxEPD2_2IC_420_A03.h"
#undef private
#include <iostream>
int main(){
 GxEPD2_2IC_420_A03 p(8,7,25,17,24);
 p._using_partial_mode=false;p._Init_Part();p.refresh(true);p._PowerOff();
 std::cout<<"[";
 for(size_t i=0;i<p.trace.size();i++){
  auto&e=p.trace[i];if(i)std::cout<<",";
  std::cout<<"["<<int(e.command)<<","<<int(e.target)<<",[";
  for(size_t j=0;j<e.data.size();j++){if(j)std::cout<<",";std::cout<<int(e.data[j]);}
  std::cout<<"]]";
 }
 std::cout<<"]";
}
'''

def without_power_on(trace):
 result=[];i=0
 while i<len(trace):
  if trace[i]==[0x22,0,[0xc0]]:
   assert trace[i+1]==[0x20,0,[]];i+=2
  else:result.append(trace[i]);i+=1
 return result

def verify(destination):
 root=Path(__file__).resolve().parents[1];destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory() as tmp:
  work=Path(tmp);(work/'epd').mkdir()
  for name in ('GxEPD2_2IC_420_A03.cpp','GxEPD2_2IC_420_A03.h'):shutil.copy(root/'evidence/upstream'/name,work/'epd'/name)
  (work/'GxEPD2_2IC_EPD.h').write_text(BASE);(work/'main.cpp').write_text(MAIN)
  subprocess.run(['c++','-std=c++17',str(work/'main.cpp'),str(work/'epd/GxEPD2_2IC_420_A03.cpp'),'-o',str(work/'oracle')],check=True,capture_output=True,timeout=30)
  reference=json.loads(subprocess.check_output([str(work/'oracle')],timeout=5))
 t=mock_transport(Config(spacing=0),Budget(60,FakeClock()));p=Panel(t);p.init();p.write_frame(b'\xff'*15000);p.refresh();p.power_off();t.spi.writes.clear()
 frame=bytearray(b'\xff'*15000)
 for y in (0,100,299):frame[y*50+25]=0
 p.update_changed(b'\xff'*15000,frame);p.power_off()
 trace=[]
 for targets,dc,payload in t.spi.writes:
  if not dc:trace.append([payload[0],0 if len(targets)==2 else 1 if targets==('cs1',) else 2,[]])
  else:trace[-1][2].extend(payload)
 p.close()
 lut=next(i for i,r in enumerate(trace) if r[0]==0x32)
 ref_lut=next(i for i,r in enumerate(reference) if r[0]==0x32)
 assert trace[:lut+1]==reference[:ref_lut+1],'Partial initialization differs'
 last_write=max(i for i,r in enumerate(trace) if r[0]==0x24)
 assert without_power_on(trace[last_write+1:])==without_power_on(reference[ref_lut+1:]),'Partial scan/activation differs'
 result={'status':'PASS','partial_init':'Exact upstream trace','scan_and_activation':'Exact refresh(true) / power-off trace, apart from established deferred power-on','dirty_bands':3,'partial_activations':1}
 (destination/'partial-reference-sequence.json').write_text(json.dumps(reference,indent=2)+'\n')
 (destination/'partial-reference-result.json').write_text(json.dumps(result,indent=2)+'\n')
 return result
if __name__=='__main__':print(json.dumps(verify(sys.argv[1] if len(sys.argv)>1 else 'evidence/software/snow-reference'),indent=2))
