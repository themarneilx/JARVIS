import {execFileSync} from 'node:child_process'
import {writeFileSync} from 'node:fs'
const results={at:new Date().toISOString()}
for(const [key,cmd,args] of [
 ['ram','free',['-b']],['gpu','nvidia-smi',['--query-gpu=name,memory.total,memory.used,utilization.gpu,temperature.gpu','--format=csv,noheader']],['ollama','ollama',['--version']],['placement','ollama',['ps']],['hyprland','hyprctl',['-j','activewindow']],['audio','wpctl',['status']],['wireplumber','systemctl',['--user','is-active','pipewire.service','wireplumber.service']]
]){
 try{results[key]=execFileSync(cmd,args,{encoding:'utf8',timeout:5000,stdio:['ignore','pipe','pipe']}).trim()}catch{results[key]={available:false}}
}
writeFileSync('.runtime/doctor.json',JSON.stringify(results,null,2),{mode:0o600})
// Do not print window titles or the complete private device inventory in routine reports.
console.log(JSON.stringify({...results,hyprland:typeof results.hyprland==='string'?'connected':results.hyprland,audio:typeof results.audio==='string'?'connected':results.audio},null,2))
