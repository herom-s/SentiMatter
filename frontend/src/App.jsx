import { useState, useRef, useEffect, useCallback } from "react";
import "./App.css";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const POSITIVE = new Set([
  "admiration","amusement","approval","caring","curiosity","excitement",
  "gratitude","joy","love","optimism","pride","relief",
]);

const NEGATIVE = new Set([
  "anger","annoyance","disappointment","disapproval","disgust",
  "embarrassment","fear","grief","nervousness","remorse","sadness",
]);

const EMOTION_COLORS = {
  admiration:"#f59e0b", amusement:"#10b981", anger:"#ef4444", annoyance:"#f97316",
  approval:"#22d3ee", caring:"#ec4899", confusion:"#8b5cf6", curiosity:"#06b6d4",
  desire:"#f43f5e", disappointment:"#94a3b8", disapproval:"#64748b", disgust:"#65a30d",
  embarrassment:"#d946ef", excitement:"#facc15", fear:"#e11d48", gratitude:"#14b8a6",
  grief:"#6b7280", joy:"#eab308", love:"#ff6b81", nervousness:"#a855f7",
  optimism:"#2dd4bf", pride:"#8b5cf6", realization:"#3b82f6", relief:"#34d399",
  remorse:"#b91c1c", sadness:"#6366f1", surprise:"#fbbf24", neutral:"#6b7280",
};

const EMOTION_ICONS = {
  admiration:"👏", amusement:"😂", anger:"😡", annoyance:"😒", approval:"👍",
  caring:"🤗", confusion:"😕", curiosity:"🤔", desire:"😍", disappointment:"😞",
  disapproval:"👎", disgust:"🤢", embarrassment:"😳", excitement:"🎉", fear:"😨",
  gratitude:"🙏", grief:"😢", joy:"🥳", love:"❤️", nervousness:"😰",
  optimism:"🌟", pride:"🦁", realization:"💡", relief:"😮‍💨", remorse:"😔",
  sadness:"😭", surprise:"😲", neutral:"😐",
};

const EMOTION_ORDER = [
  "admiration","amusement","anger","annoyance","approval","caring","confusion",
  "curiosity","desire","disappointment","disapproval","disgust","embarrassment",
  "excitement","fear","gratitude","grief","joy","love","nervousness",
  "optimism","pride","realization","relief","remorse","sadness","surprise","neutral",
];

function truncate(t, n=65) { return t.length > n ? t.slice(0,n)+"…" : t; }
function labelForPost(p,i) {
  return ["Hot","Trending","Popular","Top","Viral","Rising","Buzz","Now","Fresh","Latest"][i%10];
}
function pct(v) { return (v*100).toFixed(1); }

function category(scores) {
  let pos=0, neg=0, ntr=0;
  for (const [k,v] of Object.entries(scores)) {
    if (POSITIVE.has(k)) pos+=v;
    else if (NEGATIVE.has(k)) neg+=v;
    else ntr+=v;
  }
  const total = pos+neg+ntr || 1;
  return { pos:pct(pos/total), neg:pct(neg/total), ntr:pct(ntr/total), posRaw:pos, negRaw:neg };
}

function intensity(scores) {
  return (Object.values(scores).reduce((a,b)=>a+b,0) - (scores.neutral||0)).toFixed(2);
}

/* ── Components ── */

function EmotionBar({ label, score, isDominant, index }) {
  const p = Math.max(score*100, 0.3);
  const color = EMOTION_COLORS[label]||"#6b7280";
  const icon = EMOTION_ICONS[label]||"";
  const cat = POSITIVE.has(label) ? "pos" : NEGATIVE.has(label) ? "neg" : "ntr";
  return (
    <div className={`bar ${isDominant?"dominant":""} bar--${cat}`} style={{animationDelay:`${index*20}ms`}}>
      <span className="bar-label" title={label}>{icon} {label}</span>
      <div className="bar-track"><div className="bar-fill" style={{width:`${p}%`,background:color}}/></div>
      <span className="bar-score">{pct(score)}%</span>
    </div>
  );
}

function EmotionSection({ title, icon, scores, dominantEmotion, open }) {
  const sorted = EMOTION_ORDER.map(e=>({label:e,score:scores[e]||0})).sort((a,b)=>b.score-a.score);
  const top5 = sorted.slice(0,5);
  const cat = category(scores);
  const intense = intensity(scores);
  return (
    <details className="section" open={open}>
      <summary className="section-hd">
        <span className="section-hd-title">{icon} {title}</span>
        <div className="section-hd-chips">
          <span className="chip chip--pos">{cat.pos}% ↑</span>
          <span className="chip chip--neg">{cat.neg}% ↓</span>
          <span className="chip chip--intense">∑ {intense}</span>
        </div>
        <span className="section-chev">▾</span>
      </summary>
      <div className="section-bd">
        <div className="bars">
          {sorted.map(({label,score},i)=>(
            <EmotionBar key={label} label={label} score={score}
              isDominant={label===dominantEmotion} index={i} />
          ))}
        </div>
      </div>
    </details>
  );
}

function SummaryCard({ scores }) {
  const agg = scores?.aggregated||{};
  const dom = scores?.dominant_emotion||"";
  const dcolor = EMOTION_COLORS[dom]||"#7c5cfc";
  const dicon = EMOTION_ICONS[dom]||"🔮";
  const cat = category(agg);
  const intense = intensity(agg);
  const top3 = EMOTION_ORDER.map(e=>({label:e,score:agg[e]||0})).sort((a,b)=>b.score-a.score).slice(0,3);

  return (
    <div className="summary" style={{borderColor:dcolor+"44"}}>
      <div className="summary-glow" style={{background:`radial-gradient(ellipse at center, ${dcolor}18 0%, transparent 70%)`}}/>
      <div className="summary-main">
        <div className="summary-emotion">
          <span className="summary-emoji">{dicon}</span>
          <div>
            <span className="summary-label">Dominant</span>
            <span className="summary-name" style={{color:dcolor}}>{dom}</span>
            <span className="summary-pct">{pct(agg[dom]||0)}%</span>
          </div>
        </div>
        <div className="summary-balance">
          <span className="summary-bal-label">Sentiment balance</span>
          <div className="balance-bar-wrap">
            <div className="balance-bar">
              <div className="balance-fill balance-fill--pos" style={{width:`${cat.posRaw/(cat.posRaw+cat.negRaw+0.001)*100}%`}}/>
              <div className="balance-fill balance-fill--neg" style={{width:`${cat.negRaw/(cat.posRaw+cat.negRaw+0.001)*100}%`}}/>
            </div>
            <div className="balance-labels">
              <span style={{color:"#34d399"}}>↑ {cat.pos}%</span>
              <span style={{color:"#f87171"}}>↓ {cat.neg}%</span>
            </div>
          </div>
        </div>
      </div>
      <div className="summary-foot">
        {top3.map(e=>(
          <span key={e.label} className="summary-tag" style={{background:EMOTION_COLORS[e.label]+"22",color:EMOTION_COLORS[e.label]}}>
            {EMOTION_ICONS[e.label]} {e.label} {pct(e.score)}%
          </span>
        ))}
        <span className="summary-tag summary-tag--dim">Intensity {intense}</span>
      </div>
    </div>
  );
}

function PostCard({ post }) {
  return (
    <div className="post-card">
      <h2 className="post-title">{post.title}</h2>
      <div className="post-meta">
        <span>✍️ {post.author}</span><span className="dot">·</span>
        <span>⬆️ {post.score?.toLocaleString()??0}</span><span className="dot">·</span>
        <span>💬 {post.comments?.length??0}</span>
      </div>
      {post.text && (
        <details className="post-body-toggle">
          <summary>Show body text</summary>
          <p className="post-body">{post.text}</p>
        </details>
      )}
    </div>
  );
}

function RecentList({ recent, onSelect }) {
  if (!recent.length) return null;
  return (
    <div className="recent">
      <span className="recent-label">Recently analyzed</span>
      <div className="recent-list">
        {recent.map((item,i)=>(
          <button key={i} className="recent-chip" onClick={()=>onSelect(item.url)} title={item.url}>
            <span className="recent-n">{i+1}</span>
            <span className="recent-t">{truncate(item.title,50)}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

/* ── App ── */

export default function App() {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);
  const [examples, setExamples] = useState([]);
  const [examplesError, setExamplesError] = useState(false);
  const [recent, setRecent] = useState([]);
  const resultsRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    fetch(`${API_URL}/top-posts?limit=10`)
      .then(r=>r.ok?r.json():Promise.reject())
      .then(setExamples).catch(()=>setExamplesError(true));
    try {
      const stored = JSON.parse(localStorage.getItem("sentimatter_recent")||"[]");
      setRecent(stored);
    } catch {}
  }, []);

  const addRecent = useCallback((url, title) => {
    setRecent(prev => {
      const next = [{url,title}, ...prev.filter(r=>r.url!==url)].slice(0,5);
      try { localStorage.setItem("sentimatter_recent", JSON.stringify(next)); } catch {}
      return next;
    });
  }, []);

  const handleSubmit = async (e, overrideUrl) => {
    e?.preventDefault();
    const target = overrideUrl || url.trim();
    if (!target) return;
    setUrl(target);
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const res = await fetch(`${API_URL}/analyze`, {
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({url:target}),
      });
      if (!res.ok) {
        const text = await res.text();
        let msg;
        try { msg = JSON.parse(text).detail; } catch { msg = ""; }
        throw new Error(msg || "Backend is unreachable — make sure the API server is running");
      }
      const json = await res.json();
      setData(json);
      addRecent(target, json.post.title);
      setTimeout(()=>resultsRef.current?.scrollIntoView({behavior:"smooth",block:"start"}),100);
    } catch (err) { setError(err.message); }
    finally { setLoading(false); }
  };

  const loadExample = (u) => { setUrl(u); setData(null); setError(null); handleSubmit(null, u); };

  return (
    <div className="app">
      <header className="hd">
        <div className="hd-glow"/>
        <h1 className="hd-logo">SentiMatter</h1>
        <p className="hd-sub">Scrape any Reddit post and get a full 28-emotion sentiment breakdown</p>
      </header>

      <form className="form" onSubmit={handleSubmit}>
        <div className="form-row">
          <input ref={inputRef} className="form-input" type="url"
            placeholder="https://www.reddit.com/r/.../comments/..."
            value={url} onChange={e=>setUrl(e.target.value)} disabled={loading} required />
          <button className="form-btn" type="submit" disabled={loading}>
            {loading ? "Analyzing…" : "Analyze"}
          </button>
        </div>
      </form>

      <RecentList recent={recent} onSelect={loadExample}/>

      <div className="ex">
        <span className="ex-label">Today's top posts:</span>
        {examplesError ? (
          <span className="ex-err">Could not load top posts — paste a URL manually to analyze</span>
        ) : examples.length === 0 ? (
          <span className="ex-load"><span className="ex-spin"/><span>Loading…</span></span>
        ) : (
          <div className="ex-grid">
            {examples.map((ex,i)=>(
              <button key={ex.url} className="ex-chip" onClick={()=>loadExample(ex.url)} disabled={loading}>
                <span className="ex-chip-l1">{labelForPost(ex,i)} · r/{ex.subreddit}</span>
                <span className="ex-chip-l2" title={ex.title}>{truncate(ex.title)}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {error && <div className="err"><span>⚠️</span> {error}</div>}

      {loading && (
        <div className="load">
          <div className="load-spin"/><p>Analyzing post…</p>
          <p className="load-sub">The model runs locally so this may take a moment</p>
        </div>
      )}

      {data && (
        <div className="results" ref={resultsRef}>
          <span className="elapsed">Done in {data.elapsed}s</span>
          <SummaryCard scores={data.sentiment}/>
          <PostCard post={data.post}/>
          <div className="sections">
            <EmotionSection title="Title" icon="🏷️" scores={data.sentiment.title}
              dominantEmotion={data.sentiment.dominant_emotion}/>
            <EmotionSection title="Body" icon="📄" scores={data.sentiment.body}
              dominantEmotion={data.sentiment.dominant_emotion}/>
            <EmotionSection title="Comments" icon="💬" scores={data.sentiment.comments_avg}
              dominantEmotion={data.sentiment.dominant_emotion}/>
            <EmotionSection title="Aggregated (20/30/50)" icon="📊"
              scores={data.sentiment.aggregated} dominantEmotion={data.sentiment.dominant_emotion} open/>
          </div>
        </div>
      )}
    </div>
  );
}
