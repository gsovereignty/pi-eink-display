"""Compile the pinned upstream driver against a recording Arduino/base shim.

No hardware. Executes upstream writeImage(400x300) and captures its two RAM
streams; proves the Python row split against actual reference C++ behaviour.
"""
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

BASE = r'''
#pragma once
#include <cstdint>
#include <vector>
#include <string>
#include <utility>
#define HIGH 1
#define PROGMEM
inline void delay(int) {}
namespace GxEPD2 { enum Panel { GDEH042A03 }; }
class GxEPD2_2IC_EPD {
public:
  bool _initial_write=false, _initial_refresh=false, _using_partial_mode=true;
  bool _power_is_on=false, _hibernating=false;
  int _rst=17;
  std::vector<uint8_t> planes[2];
  uint8_t current[2]={0,0};
  struct Event {uint8_t command, target; std::vector<uint8_t> data;};
  std::vector<Event> trace;
  GxEPD2_2IC_EPD(int,int,int,int,int,int,int,int,int,GxEPD2::Panel,bool,bool,bool){}
  void _reset(){}
  void _waitWhileBusy(const char*,uint16_t){}
  void _writeCommand(uint8_t c,uint8_t m=0){
    trace.push_back({c,m,{}});
    if(m!=2) current[0]=c;
    if(m!=1) current[1]=c;
  }
  void _writeData(uint8_t d,uint8_t m=0){
    if(!trace.empty())trace.back().data.push_back(d);
    if(m!=2 && current[0]==0x24) planes[0].push_back(d);
    if(m!=1 && current[1]==0x24) planes[1].push_back(d);
  }
  void _writeCommandDataPGM(const uint8_t* p,uint16_t n){
    _writeCommand(p[0]); for(uint16_t i=1;i<n;i++)_writeData(p[i]);
  }
};
'''
MAIN = r'''
#define private public
#include "epd/GxEPD2_2IC_420_A03.h"
#undef private
#include <fstream>
int main(int argc,char**argv) {
  GxEPD2_2IC_420_A03 panel(8,7,25,17,24);
  std::vector<uint8_t> frame(15000);
  for(int y=0;y<300;y++)for(int b=0;b<50;b++)
    frame[y*50+b]=(y*31+b*13+(b/25)*71)&255;
  panel.writeImage(frame.data(),0,0,400,300,false,false,false);
  for(int c=0;c<2;c++){
    std::ofstream f(std::string(argv[1])+"/reference-cs"+std::to_string(c+1)+".bin",std::ios::binary);
    f.write((char*)panel.planes[c].data(),panel.planes[c].size());
  }
  GxEPD2_2IC_420_A03 sequence(8,7,25,17,24);
  sequence._Init_Full();sequence._Update_Full();sequence.hibernate();
  std::ofstream trace(std::string(argv[1])+"/reference-sequence.json");
  trace<<"[";
  for(size_t i=0;i<sequence.trace.size();i++){
    const auto&e=sequence.trace[i];if(i)trace<<",";
    trace<<"["<<int(e.command)<<","<<int(e.target)<<",[";
    for(size_t j=0;j<e.data.size();j++){if(j)trace<<",";trace<<int(e.data[j]);}
    trace<<"]]";
  }
  trace<<"]";
}
'''


def verify(destination):
    from hink_diag.images import split_rows
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    compiler = shutil.which("c++")
    if not compiler:
        raise RuntimeError("C++ compiler unavailable: reference oracle NOT RUN")
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        (work/"epd").mkdir()
        for name in ("GxEPD2_2IC_420_A03.cpp", "GxEPD2_2IC_420_A03.h"):
            shutil.copy(root/"evidence/upstream"/name, work/"epd"/name)
        (work/"GxEPD2_2IC_EPD.h").write_text(BASE)
        (work/"main.cpp").write_text(MAIN)
        subprocess.run([compiler,"-std=c++17",str(work/"main.cpp"),
                        str(work/"epd/GxEPD2_2IC_420_A03.cpp"),"-o",str(work/"oracle")],
                       check=True, capture_output=True, timeout=30)
        subprocess.run([str(work/"oracle"),str(destination)],check=True,timeout=5)
    frame = bytes((y*31+b*13+(b//25)*71)&255 for y in range(300) for b in range(50))
    record = {"status":"PASS", "source":"GxEPD2_2IC_420_A03.cpp", "compiler":compiler, "planes":[]}
    for c, expected in enumerate(split_rows(frame),1):
        actual = (destination/f"reference-cs{c}.bin").read_bytes()
        if actual != expected:
            raise AssertionError(f"Reference CS{c} mismatch")
        record["planes"].append({"select":c,"length":len(actual),"sha256":hashlib.sha256(actual).hexdigest()})
    from hink_diag.config import Config
    from hink_diag.transport import Budget, FakeClock, mock_transport
    from hink_diag.panel import Panel
    transport=mock_transport(Config(),Budget(60,FakeClock()))
    panel=Panel(transport);panel.init();panel.power_on();panel.refresh();panel.sleep();panel.close()
    trace=[]
    for targets,dc,payload in transport.spi.writes:
        if dc==0:trace.append([payload[0],0 if len(targets)==2 else 1 if targets==("cs1",) else 2,[]])
        else:trace[-1][2].extend(payload)
    actual=json.loads((destination/"reference-sequence.json").read_text())
    if trace!=actual:raise AssertionError(f"Full init/refresh/sleep differs from upstream: {trace} != {actual}")
    record["initialization_refresh_sleep_trace"]="PASS"
    (destination/"reference-oracle.json").write_text(json.dumps(record,indent=2)+"\n")
    return record


if __name__ == "__main__":
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    print(json.dumps(verify(sys.argv[1] if len(sys.argv)>1 else "evidence/software"),indent=2))
