import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, GitFork, Pause, Play, RotateCcw, Sparkles } from "lucide-react";
import { api } from "./api";
import type { PublicReplay } from "./types";

const eventText=(event:PublicReplay["events"][number])=>String(event.payload.content||event.payload.description||event.payload.title||event.type);

export function PublicReplayPage({token}:{token:string}){
  const [replay,setReplay]=useState<PublicReplay|null>(null);
  const [error,setError]=useState("");
  const [cursor,setCursor]=useState(0);
  const [playing,setPlaying]=useState(true);
  const [speed,setSpeed]=useState(1);
  useEffect(()=>{api.publicReplay(token).then(value=>{setReplay(value);setCursor(Math.min(1,value.events.length))}).catch(value=>setError((value as Error).message))},[token]);
  const visible=useMemo(()=>replay?.events.slice(0,cursor).filter(event=>event.type.startsWith("message.")||event.type.startsWith("constructive.")||event.type==="run.completed")||[],[replay,cursor]);
  useEffect(()=>{if(!playing||!replay||cursor>=replay.events.length)return;const timer=window.setTimeout(()=>setCursor(value=>value+1),Math.max(220,900/speed));return()=>window.clearTimeout(timer)},[playing,replay,cursor,speed]);
  if(error)return <main className="replayerror"><Sparkles/><h1>Replay unavailable</h1><p>{error}</p><button onClick={()=>location.assign(location.pathname)}><ArrowLeft/>Back to Orbit</button></main>;
  if(!replay)return <main className="replayloading"><i/><span>Loading team replay…</span></main>;
  const verdict=[...replay.artifacts].reverse().find(item=>item.kind==="trading_verdict"||item.kind==="verdict")?.metadata||replay.verdict;
  const result=[...replay.artifacts].reverse().find(item=>item.kind==="final_output"||item.kind==="working_document");
  return <main className="publicreplay">
    <header><button className="replaybrand" onClick={()=>location.assign(location.pathname)}><span/><b>Orbit</b></button><div><span>PUBLIC TEAM REPLAY</span><b>{replay.run.mode}</b></div><button className="replayfork" onClick={()=>{sessionStorage.setItem("orbit-fork-replay",token);location.assign(location.pathname)}}><GitFork/>Fork this team</button></header>
    <section className="replayhero"><p>DECISION TIMELINE</p><h1>{replay.run.goal}</h1><div className="replayteam">{replay.agents.map(agent=><span key={agent.id}><i>{agent.name.split(" ").map(x=>x[0]).join("").slice(0,2)}</i><b>{agent.name}</b><small>{agent.role} · {agent.model}</small></span>)}</div></section>
    <section className="replaybody"><div className="replaytimeline">{visible.map((event,index)=>{const agent=replay.agents.find(item=>item.id===event.actor_id);return <article key={event.id} className={index===visible.length-1?"active":""}><i/><div><header><b>{agent?.name||event.actor_type}</b><span>{event.type}</span><time>{new Date(event.created_at).toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"})}</time></header><p>{eventText(event)}</p></div></article>})}</div><aside>{verdict&&<VerdictSummary verdict={verdict}/>}<section className="replayresult"><p>FINAL ARTIFACT</p><h2>{result?.name||"Result"}</h2><pre>{result?.content||"The final artifact is still being assembled."}</pre></section></aside></section>
    <footer className="replaycontrols"><button onClick={()=>{setCursor(0);setPlaying(true)}} title="Restart"><RotateCcw/></button><button className="play" onClick={()=>setPlaying(value=>!value)}>{playing?<Pause/>:<Play/>}</button><input aria-label="Replay position" type="range" min="0" max={replay.events.length} value={cursor} onChange={event=>{setCursor(Number(event.target.value));setPlaying(false)}}/><span>{cursor}/{replay.events.length}</span><button onClick={()=>setSpeed(value=>value===1?2:value===2?0.5:1)}>{speed}×</button></footer>
  </main>
}

function VerdictSummary({verdict}:{verdict:Record<string,unknown>}){
  const list=(value:unknown)=>Array.isArray(value)?value.map(String):value?[String(value)]:[];
  return <section className="replayverdict"><p>TEAM VERDICT</p><h2>{String(verdict.decision||"Decision ready")}</h2><div className="agreement"><strong>{String(verdict.agreement||0)}/{String(verdict.total_agents||0)}</strong><span>agents aligned</span></div>{list(verdict.dissent).length>0&&<div><b>Dissent preserved</b>{list(verdict.dissent).map(item=><span key={item}>{item}</span>)}</div>}{list(verdict.open_questions).length>0&&<div><b>Open questions</b>{list(verdict.open_questions).map(item=><span key={item}>{item}</span>)}</div>}</section>
}
