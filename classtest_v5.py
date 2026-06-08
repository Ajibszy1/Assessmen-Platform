import streamlit as st
import pandas as pd
import time
import random
import hashlib
import json
import io
from datetime import datetime
from supabase import create_client, Client

st.set_page_config(page_title="Secure Assessment Platform", layout="wide", initial_sidebar_state="collapsed")

PASS_MARK        = 50
MAX_TAB_SWITCHES = 2
MAX_RETAKES      = 1

# =====================================================================
# SUPABASE CLIENT
# =====================================================================
@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["service_role_key"]
    return create_client(url, key)

def db() -> Client:
    return get_supabase()

def get_admin_credentials():
    try: return st.secrets["admin"]["email"], st.secrets["admin"]["password"]
    except Exception: return "admin@academy.com", "admin123"

# =====================================================================
# DB HELPERS
# =====================================================================
def db_all(table, filters=None):
    try:
        q = db().table(table).select("*")
        if filters:
            for col, val in filters.items():
                q = q.eq(col, val)
        r = q.execute()
        return pd.DataFrame(r.data) if r.data else pd.DataFrame()
    except Exception as e:
        st.error(f"DB read error ({table}): {e}")
        return pd.DataFrame()

def db_insert(table, row):
    try:
        db().table(table).insert(row).execute()
        return True
    except Exception as e:
        st.error(f"DB insert error ({table}): {e}")
        return False

def db_upsert(table, row, on_conflict):
    try:
        db().table(table).upsert(row, on_conflict=on_conflict).execute()
        return True
    except Exception as e:
        st.error(f"DB upsert error ({table}): {e}")
        return False

def db_update(table, match, data):
    try:
        q = db().table(table)
        for col, val in match.items():
            q = q.eq(col, val)
        q.update(data).execute()
        return True
    except Exception as e:
        st.error(f"DB update error ({table}): {e}")
        return False

def db_delete(table, match):
    try:
        q = db().table(table)
        for col, val in match.items():
            q = q.eq(col, val)
        q.delete().execute()
        return True
    except Exception as e:
        st.error(f"DB delete error ({table}): {e}")
        return False

def db_one(table, filters):
    df = db_all(table, filters)
    return df.iloc[0].to_dict() if not df.empty else None

# =====================================================================
# HELPERS
# =====================================================================
def make_device_id(email):
    if "browser_token" not in st.session_state:
        st.session_state.browser_token = hashlib.sha256(
            f"{email}{time.time()}{random.random()}".encode()).hexdigest()[:16]
    return hashlib.sha256(f"{email}_{st.session_state.browser_token}".encode()).hexdigest()[:16]

def compute_score(questions, answers, overrides=None):
    if overrides is None: overrides = {}
    correct = 0
    for i, q in enumerate(questions):
        key = f"q_{i}"; ov = overrides.get(key)
        if ov is not None:
            if ov: correct += 1
        else:
            if str(answers.get(key,"")).strip().lower() == str(q["answer"]).strip().lower():
                correct += 1
    total = len(questions)
    return correct, total, round((correct/total*100) if total>0 else 0, 2)

def read_file(f):
    name = f.name.lower()
    if name.endswith(".csv"): return pd.read_csv(f)
    elif name.endswith((".xlsx",".xls")): return pd.read_excel(f)
    raise ValueError("Only CSV or Excel supported.")

def validate_questions(df):
    missing = [c for c in ["question","answer","type"] if c not in df.columns]
    if missing: return False, f"Missing columns: {', '.join(missing)}"
    if df.empty: return False, "No data rows."
    inv = df[~df["type"].isin(["mcq","short"])]["type"].unique()
    if len(inv): return False, f"Invalid types: {list(inv)}. Use 'mcq' or 'short'."
    return True, ""

def build_excel(df):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Results")
        wb = writer.book; ws = writer.sheets["Results"]
        hdr = wb.add_format({"bold":True,"bg_color":"#667eea","font_color":"white","border":1,"align":"center"})
        pf  = wb.add_format({"bg_color":"#d1fae5","border":1})
        ff  = wb.add_format({"bg_color":"#fee2e2","border":1})
        for ci, val in enumerate(df.columns):
            ws.write(0, ci, val, hdr)
            ws.set_column(ci, ci, max(15, len(str(val))+4))
        if "percentage" in df.columns:
            pc = df.columns.get_loc("percentage")
            for ri, pct in enumerate(df["percentage"], start=1):
                try: ws.write(ri, pc, pct, pf if float(pct)>=PASS_MARK else ff)
                except Exception: pass
    buf.seek(0); return buf

def get_security_js():
    return f"""<script>
    (function(){{
        let v=0,lw=0;const MAX={MAX_TAB_SWITCHES};
        function goFS(){{const e=document.documentElement;
            if(e.requestFullscreen) e.requestFullscreen();
            else if(e.webkitRequestFullscreen) e.webkitRequestFullscreen();}}
        document.addEventListener('click',function t(){{goFS();document.removeEventListener('click',t);}},{{once:true}});
        document.addEventListener('fullscreenchange',()=>{{if(!document.fullscreenElement){{handleV();setTimeout(goFS,1000);}}}});
        function showW(msg,fin=false){{
            const now=Date.now();if(!fin&&now-lw<3000)return;lw=now;
            const old=document.getElementById('ew');if(old)old.remove();
            const d=document.createElement('div');d.id='ew';
            d.style.cssText='position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(220,38,38,0.95);z-index:999999;display:flex;align-items:center;justify-content:center;';
            d.innerHTML='<div style="background:white;padding:40px;border-radius:16px;max-width:500px;text-align:center;"><div style="font-size:64px;">⚠️</div><h2 style="color:#dc2626;">'+(fin?'EXAM TERMINATED':'SECURITY WARNING')+'</h2><p style="font-size:18px;white-space:pre-line;">'+msg+'</p>'+(!fin?'<button onclick="document.getElementById(\\'ew\\').remove()" style="margin-top:20px;padding:12px 32px;background:#dc2626;color:white;border:none;border-radius:8px;font-size:16px;cursor:pointer;">I Understand</button>':'')+'</div>';
            document.body.appendChild(d);}}
        function handleV(){{if(v>MAX)return;v++;
            if(v<=MAX) showW('Warning '+v+'/'+(MAX+1)+':\\n\\nYou left the exam window.\\n\\nAnother violation = auto-submit.');
            else{{showW('Max violations.\\n\\nSubmitting now...',true);setTimeout(()=>{{window.location.href='?auto_submit=1';}},2000);}}}}
        document.addEventListener('visibilitychange',()=>{{if(document.hidden)handleV();}});
        window.addEventListener('blur',()=>handleV());
        document.addEventListener('keydown',(e)=>{{
            if(e.key==='PrintScreen'||e.key==='F12'||(e.ctrlKey&&e.shiftKey&&e.key==='I')||(e.metaKey&&e.shiftKey&&['3','4','5'].includes(e.key))){{
                e.preventDefault();showW('Screenshot detected!\\n\\nThis has been recorded.');}}
            if(e.altKey)e.preventDefault();}});
        document.addEventListener('contextmenu',e=>e.preventDefault());
        document.addEventListener('copy',e=>e.preventDefault());
        document.addEventListener('paste',e=>e.preventDefault());
    }})();</script>"""

st.markdown("""
<style>
    .stApp > header,.stAppHeader,[data-testid="stHeader"],[data-testid="stToolbar"],
    .stDeployButton,.viewerBadge_container__r5tak{display:none !important;}
    #MainMenu,footer{visibility:hidden;}
    #root > div:first-child{margin-top:0 !important;}
    .main .block-container{padding-top:1rem !important;max-width:100% !important;}
    .stApp{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%) !important;}
    *{font-family:'Inter',sans-serif;}
    .exam-container{background:white;border-radius:20px;padding:2.5rem;
        box-shadow:0 25px 80px rgba(0,0,0,0.2);max-width:920px;margin:1.5rem auto;}
    .question-card{background:#f8fafc;border-left:5px solid #667eea;
        padding:1.5rem;margin:1.5rem 0;border-radius:12px;}
    .instruction-box{background:#eff6ff;border:2px solid #667eea;
        border-radius:16px;padding:2rem;margin:1rem 0;}
    .stButton>button{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);
        color:white;border:none;padding:0.875rem 2.5rem;
        border-radius:10px;font-weight:700;width:100%;}
    .score-circle{width:180px;height:180px;border-radius:50%;
        display:flex;align-items:center;justify-content:center;
        margin:0 auto 2rem;color:white;font-size:3rem;font-weight:800;}
    .lb-row{display:flex;align-items:center;padding:0.75rem 1rem;
        border-radius:10px;margin:0.4rem 0;background:#f1f5f9;}
    .lb-rank{font-size:1.5rem;font-weight:800;width:48px;}
    .lb-name{flex:1;font-weight:600;}
    .lb-score{font-size:1.1rem;font-weight:700;color:#667eea;}
    .lb-gold{background:linear-gradient(90deg,#fef9c3,#fde68a);}
    .lb-silver{background:linear-gradient(90deg,#f1f5f9,#e2e8f0);}
    .lb-bronze{background:linear-gradient(90deg,#fff7ed,#fed7aa);}
</style>""", unsafe_allow_html=True)

for k,v in {"page":"login","answers":{},"questions":[],"current_course":None,
    "show_correction":False,"result_saved":False,"start_time":None,
    "student_name":"","student_email":"","device_id":None,"tab_violations":0,
    "security_js_injected":False,"show_admin_login":False,"admin_auth":False,
    "confirm_submit":False,"last_save_time":0,"browser_token":None,
    "auto_submitted":False,"attempt_num":1,"instructions_accepted":False}.items():
    if k not in st.session_state: st.session_state[k]=v

if st.query_params.get("auto_submit")=="1":
    if st.session_state.page=="quiz":
        st.session_state.page="result"; st.session_state.auto_submitted=True
        st.query_params.clear(); st.rerun()

# =====================================================================
# LOGIN
# =====================================================================
if st.session_state.page=="login":
    ca,cb=st.columns([12,1])
    with cb:
        if st.button("🔒",help="Admin"):
            st.session_state.show_admin_login=not st.session_state.show_admin_login; st.rerun()
    st.markdown('<div class="exam-container">',unsafe_allow_html=True)
    st.title("🎓 Assessment Portal")
    st.markdown("---")
    if st.session_state.show_admin_login:
        with st.expander("🛡️ Admin Login",expanded=True):
            ae=st.text_input("Admin Email",key="aei")
            ap=st.text_input("Password",type="password",key="api_p")
            if st.button("🔑 Login as Admin",use_container_width=True):
                AE,AP=get_admin_credentials()
                if ae==AE and ap==AP:
                    st.session_state.admin_auth=True; st.session_state.page="admin"; st.rerun()
                else: st.error("❌ Invalid credentials")
        st.markdown("---")
    st.subheader("Student Login")
    email=st.text_input("Your Email Address",key="login_email")
    access_code=st.text_input("Course Access Code",type="password",key="login_code",help="Given by your instructor")
    if st.button("🚀 Login",use_container_width=True):
        email=email.strip().lower(); code=access_code.strip().upper()
        if not email or not code: st.error("⚠️ Enter email and access code."); st.stop()
        with st.spinner("Verifying..."):
            student=db_one("students",{"email":email})
        if not student: st.error("⛔ Email not registered. Contact your instructor."); st.stop()
        attempts=int(student.get("login_attempts",0) or 0)
        if attempts>=5: st.error("⛔ Too many failed attempts. Contact instructor."); st.stop()
        with st.spinner("Finding course..."):
            courses_r=db().table("courses").select("*").eq("enabled",True).eq("access_code",code).execute()
            courses=pd.DataFrame(courses_r.data) if courses_r.data else pd.DataFrame()
        if courses.empty:
            db_update("students",{"email":email},{"login_attempts":attempts+1})
            st.error("⛔ Invalid code or course not active."); st.stop()
        db_update("students",{"email":email},{"login_attempts":0})
        course=courses.iloc[0].to_dict()
        course_id=str(course["course_id"]); course_name=str(course["course_name"])
        duration=int(course.get("duration_mins",40))*60
        q_count=int(course.get("question_count",0) or 0)
        device_id=make_device_id(email)
        blk=db_one("blocked_devices",{"device_id":device_id})
        if blk and not blk.get("unblocked_at"): st.error("⛔ Device blocked. Contact instructor."); st.stop()
        attempts_r=db().table("results").select("id",count="exact").eq("email",email).eq("course_id",course_id).execute()
        attempts_done=attempts_r.count or 0
        if attempts_done>MAX_RETAKES: st.error(f"⛔ All {MAX_RETAKES+1} attempts used for **{course_name}**."); st.stop()
        attempt_num=attempts_done+1
        with st.spinner("Checking saved session..."):
            sess=db_one("active_sessions",{"email":email,"course_id":course_id})
        if sess:
            start=float(sess["start_time"]) if sess.get("start_time") else None
            if start and (time.time()-start)<=duration:
                st.session_state.update({
                    "student_name":sess["name"],"student_email":email,"device_id":device_id,
                    "questions":json.loads(sess["questions_json"]) if sess.get("questions_json") else [],
                    "answers":json.loads(sess["answers_json"]) if sess.get("answers_json") else {},
                    "start_time":start,"tab_violations":int(sess.get("tab_violations",0) or 0),
                    "attempt_num":int(sess.get("attempt_num",attempt_num) or attempt_num),
                    "current_course":course,"instructions_accepted":True,"page":"quiz"})
                st.success("🔄 Resuming saved session..."); time.sleep(0.8); st.rerun()
        with st.spinner("Loading questions..."):
            q_r=db().table("questions").select("*").eq("course_id",course_id).execute()
            q_df=pd.DataFrame(q_r.data) if q_r.data else pd.DataFrame()
        if q_df.empty: st.error("⛔ No questions found for this course."); st.stop()
        if q_count>0 and len(q_df)>q_count: q_df=q_df.sample(n=q_count).reset_index(drop=True)
        else: q_df=q_df.sample(frac=1).reset_index(drop=True)
        questions=[]
        for _,row in q_df.iterrows():
            qt=str(row.get("type","mcq")).strip().lower(); opts=[]
            if qt=="mcq":
                opts=[str(row.get(f"option{i}","")).strip() for i in range(1,5)
                      if row.get(f"option{i}") and str(row.get(f"option{i}","")).strip()]
                random.shuffle(opts)
            questions.append({"question":str(row["question"]).strip(),"options":opts,
                "answer":str(row["answer"]).strip(),"type":qt,"difficulty":str(row.get("difficulty","medium"))})
        st.session_state.update({"student_name":student["name"],"student_email":email,"device_id":device_id,
            "questions":questions,"answers":{},"start_time":None,"tab_violations":0,
            "attempt_num":attempt_num,"current_course":course,"instructions_accepted":False,"page":"instructions"})
        st.rerun()
    st.markdown('</div>',unsafe_allow_html=True)

# =====================================================================
# INSTRUCTIONS
# =====================================================================
elif st.session_state.page=="instructions":
    course=st.session_state.current_course or {}
    duration=int(course.get("duration_mins",40))
    pass_mark=int(course.get("pass_mark",PASS_MARK))
    total_q=len(st.session_state.questions)
    attempt_n=st.session_state.attempt_num
    st.markdown('<div class="exam-container">',unsafe_allow_html=True)
    st.title(f"📋 {course.get('course_name','Exam')} — Instructions")
    if attempt_n>1: st.warning(f"⚠️ This is your **Attempt {attempt_n}** of {MAX_RETAKES+1}.")
    st.markdown(f"""<div class="instruction-box">

### 📌 Before You Begin

| | |
|---|---|
| ⏱️ **Duration** | {duration} minutes |
| ❓ **Questions** | {total_q} questions |
| 🎯 **Pass Mark** | {pass_mark}% |
| 🔁 **Attempts** | {MAX_RETAKES+1} total (you are on attempt {attempt_n}) |

---

### 📜 Rules

1. **Do not switch tabs or windows.** You get {MAX_TAB_SWITCHES} warnings — then auto-submit.
2. **Do not press PrintScreen or F12** — detected and recorded.
3. **No copying or pasting** during the exam.
4. **Exam auto-submits** when the timer runs out.
5. **Progress saves** automatically every 60 seconds — you can log back in to resume.

---
✅ **By clicking Start, you agree to these rules.**
</div>""",unsafe_allow_html=True)
    c1,c2,c3=st.columns([1,2,1])
    with c2:
        if st.button("🚀 I Understand — Start Exam",use_container_width=True):
            start_time=time.time(); st.session_state.start_time=start_time
            course_id=str(course.get("course_id",""))
            sess_row={"email":st.session_state.student_email,"name":st.session_state.student_name,
                "course_id":course_id,"attempt_num":st.session_state.attempt_num,"page":"quiz",
                "answers_json":json.dumps({}),"questions_json":json.dumps(st.session_state.questions),
                "start_time":str(start_time),"tab_violations":0,"device_id":st.session_state.device_id,
                "last_activity":datetime.now().isoformat()}
            with st.spinner("Starting..."):
                existing=db_one("active_sessions",{"email":st.session_state.student_email,"course_id":course_id})
                if existing: db_update("active_sessions",{"email":st.session_state.student_email,"course_id":course_id},sess_row)
                else: db_insert("active_sessions",sess_row)
            st.session_state.page="quiz"; st.rerun()
    st.markdown('</div>',unsafe_allow_html=True)

# =====================================================================
# QUIZ
# =====================================================================
elif st.session_state.page=="quiz":
    if not st.session_state.security_js_injected:
        st.markdown(get_security_js(),unsafe_allow_html=True)
        st.session_state.security_js_injected=True
    course=st.session_state.current_course or {}
    course_id=str(course.get("course_id",""))
    duration=int(course.get("duration_mins",40))*60
    if st.session_state.start_time is None: st.session_state.start_time=time.time()
    elapsed=time.time()-st.session_state.start_time
    remaining=duration-elapsed
    if remaining<=0: st.session_state.page="result"; st.rerun()
    mins,secs=divmod(int(max(remaining,0)),60)
    st.markdown(f"""<script>
    (function(){{let t={int(remaining)};
    function tick(){{if(t<=0){{window.location.href='?auto_submit=1';return;}}
    const m=Math.floor(t/60).toString().padStart(2,'0');const s=(t%60).toString().padStart(2,'0');
    const el=document.getElementById('lt');
    if(el){{el.textContent='⏱️ '+m+':'+s;if(t<300)el.style.background='linear-gradient(135deg,#f093fb,#f5576c)';}}
    const pr=document.getElementById('lp');if(pr)pr.style.width=(({duration}-t)/{duration}*100)+'%';
    if(t===300)alert('⚠️ 5 minutes remaining!');t--;}}
    tick();setInterval(tick,1000);}})();
    </script>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;
        background:rgba(255,255,255,0.12);padding:1rem 1.5rem;border-radius:14px;">
        <div style="color:white;">
            <h2 style="margin:0;color:white;">📝 {course.get('course_name','Assessment')}</h2>
            <p style="margin:4px 0;opacity:0.85;">{st.session_state.student_name} &nbsp;|&nbsp; Attempt {st.session_state.attempt_num} of {MAX_RETAKES+1}</p>
        </div>
        <div id="lt" style="background:linear-gradient(135deg,#667eea,#764ba2);color:white;
            padding:0.9rem 1.8rem;border-radius:12px;font-size:1.8rem;font-weight:800;
            min-width:150px;text-align:center;box-shadow:0 8px 24px rgba(0,0,0,0.3);">
            ⏱️ {mins:02d}:{secs:02d}</div></div>
    <div style="width:100%;height:8px;background:rgba(255,255,255,0.2);border-radius:5px;overflow:hidden;margin-bottom:20px;">
        <div id="lp" style="height:100%;background:linear-gradient(90deg,#a78bfa,#60a5fa);
            width:{(elapsed/duration)*100:.1f}%;transition:width 1s linear;"></div></div>""",unsafe_allow_html=True)
    total=len(st.session_state.questions)
    answered=sum(1 for v in st.session_state.answers.values() if str(v).strip())
    st.write(f"**Progress: {answered}/{total} answered**")
    for i,q in enumerate(st.session_state.questions):
        st.markdown('<div class="question-card">',unsafe_allow_html=True)
        badge={"easy":"🟢","medium":"🟡","hard":"🔴"}.get(q.get("difficulty",""),"")
        st.markdown(f"**Q{i+1} of {total}** {badge}")
        st.markdown(f"### {q['question']}")
        key=f"q_{i}"; current=st.session_state.answers.get(key,"")
        if q["type"]=="short":
            ans=st.text_input("Your answer:",value=current,key=key)
        else:
            opts=q["options"]; idx=opts.index(current) if current in opts else None
            ans=st.radio("Select your answer:",opts,index=idx,key=key)
        if ans: st.session_state.answers[key]=str(ans).strip()
        st.markdown('</div>',unsafe_allow_html=True)
    if time.time()-st.session_state.last_save_time>60:
        try:
            db_update("active_sessions",{"email":st.session_state.student_email,"course_id":course_id},
                {"answers_json":json.dumps(st.session_state.answers),"last_activity":datetime.now().isoformat()})
            st.session_state.last_save_time=time.time()
        except Exception: pass
    st.markdown("---")
    unanswered=total-answered
    if not st.session_state.confirm_submit:
        c1,c2,c3=st.columns([1,2,1])
        with c2:
            if st.button("✅ Submit Assessment",use_container_width=True,type="primary"):
                if unanswered>0: st.session_state.confirm_submit=True; st.rerun()
                else: st.session_state.page="result"; st.rerun()
    else:
        st.warning(f"⚠️ **{unanswered}** unanswered. Submit anyway?")
        c1,c2=st.columns(2)
        with c1:
            if st.button("✅ Yes, Submit",use_container_width=True): st.session_state.page="result"; st.rerun()
        with c2:
            if st.button("↩️ Go Back",use_container_width=True): st.session_state.confirm_submit=False; st.rerun()

# =====================================================================
# RESULT
# =====================================================================
elif st.session_state.page=="result":
    course=st.session_state.current_course or {}
    course_id=str(course.get("course_id",""))
    pass_mark=int(course.get("pass_mark",PASS_MARK))
    correct,total,percentage=compute_score(st.session_state.questions,st.session_state.answers)
    passed=percentage>=pass_mark
    st.markdown('<div class="exam-container" style="text-align:center;">',unsafe_allow_html=True)
    st.title("📊 Assessment Results")
    st.subheader(course.get("course_name",""))
    if st.session_state.auto_submitted: st.warning("⏰ Auto-submitted — time ran out.")
    color="#10b981" if percentage>=70 else "#f59e0b" if percentage>=50 else "#ef4444"
    st.markdown(f'<div class="score-circle" style="background:{color};">{percentage:.0f}%</div>',unsafe_allow_html=True)
    st.markdown(f"### {correct} / {total} Correct")
    st.markdown(f"**Result:** {'✅ Pass' if passed else '❌ Fail'}")
    remaining_attempts=MAX_RETAKES+1-st.session_state.attempt_num
    if not passed and remaining_attempts>0:
        st.info(f"💡 You have **{remaining_attempts}** retake(s) available. Ask your instructor.")
    if not st.session_state.result_saved:
        rd={"name":st.session_state.student_name,"email":st.session_state.student_email,
            "course_id":course_id,"course_name":course.get("course_name",""),
            "score":correct,"total":total,"percentage":round(percentage,2),
            "violations":st.session_state.tab_violations,"attempt_num":st.session_state.attempt_num,
            "start_time":datetime.fromtimestamp(st.session_state.start_time).isoformat() if st.session_state.start_time else None,
            "submit_time":datetime.now().isoformat()}
        sub_row={"email":st.session_state.student_email,"name":st.session_state.student_name,
            "course_id":course_id,"attempt_num":st.session_state.attempt_num,
            "questions_json":json.dumps(st.session_state.questions),
            "answers_json":json.dumps(st.session_state.answers),
            "overrides_json":json.dumps({}),"submit_time":datetime.now().isoformat()}
        with st.spinner("Saving..."):
            if db_insert("results",rd):
                db_insert("submissions",sub_row)
                st.session_state.result_saved=True
                db_delete("active_sessions",{"email":st.session_state.student_email,"course_id":course_id})
                if st.session_state.tab_violations>=MAX_TAB_SWITCHES:
                    db_insert("blocked_devices",{"device_id":st.session_state.device_id,
                        "reason":f"Exceeded {MAX_TAB_SWITCHES} violations","email":st.session_state.student_email,
                        "blocked_at":datetime.now().isoformat()})
    st.success("✅ Results saved.")
    if st.button("📋 View Detailed Feedback"):
        st.session_state.show_correction=not st.session_state.show_correction; st.rerun()
    if st.session_state.show_correction:
        st.markdown("---")
        for i,q in enumerate(st.session_state.questions):
            s=st.session_state.answers.get(f"q_{i}","No answer"); c=q["answer"]
            ok=str(s).strip().lower()==str(c).strip().lower()
            with st.expander(f"Q{i+1}: {'✅' if ok else '❌'} — {q['question'][:60]}..."):
                st.write(f"**Your Answer:** {s}"); st.write(f"**Correct Answer:** {c}")
    st.markdown("---")
    if st.button("🔒 Logout & Exit"):
        for k in list(st.session_state.keys()): del st.session_state[k]
        st.rerun()
    st.markdown('</div>',unsafe_allow_html=True)

# =====================================================================
# ADMIN
# =====================================================================
elif st.session_state.page=="admin":
    if not st.session_state.admin_auth: st.session_state.page="login"; st.rerun()
    st.title("🔐 Admin Control Center")
    (tab_courses,tab_students,tab_results,tab_review,tab_leader,tab_devices,tab_analytics)=st.tabs([
        "📚 Courses","👥 Students","📊 Results","🔍 Review & Correct","🏆 Leaderboard","🚫 Devices","📈 Analytics"])

    with tab_courses:
        st.subheader("Manage Courses")
        with st.expander("➕ Create / Edit Course",expanded=False):
            c1,c2=st.columns(2)
            with c1:
                cid=st.text_input("Course ID (e.g. PY101)",key="nc_id")
                cname=st.text_input("Course Name",key="nc_name")
                ccode=st.text_input("Access Code",key="nc_code").upper()
            with c2:
                cdur=st.number_input("Duration (mins)",5,300,40,key="nc_dur")
                cpas=st.number_input("Pass Mark (%)",1,100,50,key="nc_pas")
                cq=st.number_input("Questions per exam (0=all)",0,500,0,key="nc_q",
                    help="e.g. 20 = randomly pick 20 from bank each exam")
                cenab=st.toggle("Enable immediately",False,key="nc_enab")
            if st.button("💾 Save Course",use_container_width=True):
                if cid.strip() and cname.strip() and ccode.strip():
                    row={"course_id":cid.strip(),"course_name":cname.strip(),"access_code":ccode.strip(),
                         "enabled":cenab,"duration_mins":cdur,"pass_mark":cpas,"question_count":cq}
                    with st.spinner("Saving..."):
                        ok=db_upsert("courses",row,"course_id")
                    if ok: st.success(f"✅ Saved **{cname}** | Code: `{ccode}`"); st.rerun()
                else: st.warning("Fill Course ID, Name and Code.")
        st.markdown("---")
        with st.spinner("Loading..."): courses_df=db_all("courses")
        if courses_df.empty: st.info("No courses yet.")
        else:
            for _,row in courses_df.iterrows():
                cid_=str(row["course_id"]); cname_=str(row["course_name"])
                ccode_=str(row["access_code"]); enab_=bool(row.get("enabled",False))
                dur_=row.get("duration_mins",40); pas_=row.get("pass_mark",50); qcnt_=row.get("question_count",0)
                ca,cb,cc,cd=st.columns([4,2,1,1])
                with ca:
                    st.markdown(f"**{cname_}** `{cid_}`  \n{'🟢 Active' if enab_ else '🔴 Disabled'}"
                                f" | ⏱ {dur_} min | 🎯 {pas_}% | 📚 {qcnt_} Qs")
                with cb: st.code(f"Code: {ccode_}")
                with cc:
                    if st.button("Disable" if enab_ else "Enable",key=f"tog_{cid_}"):
                        db_update("courses",{"course_id":cid_},{"enabled":not enab_}); st.rerun()
                with cd:
                    if st.button("🗑️",key=f"delc_{cid_}"):
                        db_delete("courses",{"course_id":cid_}); st.rerun()
                with st.expander(f"📁 Questions — {cname_}"):
                    st.markdown("**CSV or Excel** — columns: `question`,`answer`,`type` + `option1-4` for MCQ + optional `difficulty`")
                    up=st.file_uploader(f"Upload for {cname_}",type=["csv","xlsx","xls"],key=f"up_{cid_}")
                    if up:
                        try:
                            q_df=read_file(up); valid,err=validate_questions(q_df)
                            if not valid: st.error(f"❌ {err}")
                            else:
                                st.dataframe(q_df.head(5)); st.caption(f"{len(q_df)} questions")
                                if st.button(f"✅ Save to Question Bank",key=f"saveq_{cid_}"):
                                    with st.spinner("Saving..."):
                                        db_delete("questions",{"course_id":cid_})
                                        rows=[]
                                        for _2,qrow in q_df.iterrows():
                                            rows.append({"course_id":cid_,
                                                "question":str(qrow.get("question","")),
                                                "option1":str(qrow.get("option1","")) if pd.notna(qrow.get("option1")) else "",
                                                "option2":str(qrow.get("option2","")) if pd.notna(qrow.get("option2")) else "",
                                                "option3":str(qrow.get("option3","")) if pd.notna(qrow.get("option3")) else "",
                                                "option4":str(qrow.get("option4","")) if pd.notna(qrow.get("option4")) else "",
                                                "answer":str(qrow.get("answer","")),
                                                "type":str(qrow.get("type","mcq")),
                                                "difficulty":str(qrow.get("difficulty","medium"))})
                                        if rows:
                                            for chunk in [rows[i:i+50] for i in range(0,len(rows),50)]:
                                                db().table("questions").insert(chunk).execute()
                                            db_update("courses",{"course_id":cid_},{"question_count":len(rows)})
                                        st.success(f"✅ {len(rows)} questions saved!"); st.rerun()
                        except Exception as e: st.error(f"Error: {e}")
                    cur_q=db_all("questions",{"course_id":cid_})
                    if not cur_q.empty:
                        st.caption(f"Bank: **{len(cur_q)} questions**")
                        with st.expander("Preview"):
                            st.dataframe(cur_q[["question","answer","type","difficulty"]],use_container_width=True)
                st.markdown("---")

    with tab_students:
        st.subheader("Student Management")
        c1,c2=st.columns(2)
        with c1:
            st.markdown("#### ⬆️ Bulk Upload")
            st.markdown("CSV/Excel with `Email` and `Name` columns.")
            sf=st.file_uploader("Upload",type=["csv","xlsx","xls"],key="stu_up")
            if sf:
                try:
                    sdf=read_file(sf)
                    if "Email" not in sdf.columns or "Name" not in sdf.columns:
                        st.error("❌ Need 'Email' and 'Name'.")
                    else:
                        sdf["Email"]=sdf["Email"].str.strip().str.lower()
                        st.dataframe(sdf[["Email","Name"]].head(8)); st.caption(f"{len(sdf)} students")
                        if st.button("✅ Upload List",use_container_width=True):
                            with st.spinner("Uploading..."):
                                rows=[{"email":r["Email"],"name":r["Name"],"login_attempts":0} for _,r in sdf.iterrows()]
                                for chunk in [rows[i:i+50] for i in range(0,len(rows),50)]:
                                    db().table("students").upsert(chunk,on_conflict="email").execute()
                            st.success(f"✅ {len(rows)} uploaded!"); st.rerun()
                except Exception as e: st.error(f"Error: {e}")
        with c2:
            st.markdown("#### ➕ Add Single Student")
            se=st.text_input("Email",key="add_se"); sn=st.text_input("Name",key="add_sn")
            if st.button("Add",use_container_width=True):
                if se.strip() and sn.strip():
                    ok=db_upsert("students",{"email":se.strip().lower(),"name":sn.strip(),"login_attempts":0},"email")
                    if ok: st.success(f"✅ Added {sn}"); st.rerun()
                else: st.warning("Fill both fields.")
        st.markdown("---")
        with st.spinner("Loading..."): all_stu=db_all("students")
        if all_stu.empty: st.info("No students yet.")
        else:
            st.dataframe(all_stu[["email","name","login_attempts"]],use_container_width=True)
            st.caption(f"{len(all_stu)} students")
            st.markdown("---")
            c1,c2=st.columns(2)
            with c1:
                de=st.selectbox("Remove:",[""]+all_stu["email"].tolist(),key="del_stu")
                if de and st.button("🗑️ Remove",key="del_stu_btn"):
                    db_delete("students",{"email":de}); st.success(f"Removed {de}"); st.rerun()
            with c2:
                re_=st.selectbox("Reset login attempts:",[""]+all_stu["email"].tolist(),key="rst_stu")
                if re_ and st.button("🔄 Reset",key="rst_btn"):
                    db_update("students",{"email":re_},{"login_attempts":0}); st.success(f"Reset for {re_}"); st.rerun()

    with tab_results:
        st.subheader("Results")
        with st.spinner("Loading..."): c_df=db_all("courses")
        copts=["All Courses"]+([] if c_df.empty else [f"{r['course_name']} ({r['course_id']})" for _,r in c_df.iterrows()])
        sel_cs=st.selectbox("Filter:",copts,key="res_flt")
        sel_cid=None
        if sel_cs!="All Courses" and not c_df.empty: sel_cid=sel_cs.split("(")[-1].rstrip(")")
        with st.spinner("Loading..."):
            res_df=db_all("results",{"course_id":sel_cid}) if sel_cid else db_all("results")
        if not res_df.empty:
            st.dataframe(res_df,use_container_width=True)
            st.download_button("⬇️ Download Excel",build_excel(res_df),
                f"results_{sel_cid or 'all'}_{datetime.now().strftime('%Y%m%d')}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            st.download_button("⬇️ Download CSV",res_df.to_csv(index=False),
                f"results_{sel_cid or 'all'}.csv","text/csv")
            st.markdown("---")
            st.subheader("Allow Retake")
            if not c_df.empty:
                rt_c=st.selectbox("Course:",[""]+c_df["course_id"].tolist(),key="rt_c")
                rt_e=st.selectbox("Student:",[""]+res_df["email"].tolist(),key="rt_e")
                if rt_c and rt_e:
                    cnt_r=db().table("results").select("id",count="exact").eq("email",rt_e).eq("course_id",rt_c).execute()
                    st.info(f"{rt_e} has **{cnt_r.count or 0}** attempt(s).")
                    if st.button("🗑️ Delete All Attempts (full reset)"):
                        db_delete("results",{"email":rt_e,"course_id":rt_c})
                        st.success(f"✅ Reset for {rt_e}"); st.rerun()
        else: st.info("No results yet.")

    with tab_review:
        st.subheader("🔍 Review & Correct")
        with st.spinner("Loading..."): c_df2=db_all("courses")
        if c_df2.empty: st.info("No courses.")
        else:
            rev_c=st.selectbox("Course:",["— Select —"]+[f"{r['course_name']} ({r['course_id']})" for _,r in c_df2.iterrows()],key="rev_c")
            if rev_c!="— Select —":
                rev_cid=rev_c.split("(")[-1].rstrip(")")
                with st.spinner("Loading..."): subs=db_all("submissions",{"course_id":rev_cid})
                if subs.empty: st.info("No submissions yet.")
                else:
                    seen=set(); unique=[]
                    for _,r in subs.iterrows():
                        if r["email"] not in seen: seen.add(r["email"]); unique.append((r["email"],r["name"]))
                    sub_opts=[f"{n} ({e})" for e,n in unique]
                    sel_sub=st.selectbox("Student:",["— Select —"]+sub_opts,key="rev_stu")
                    if sel_sub!="— Select —":
                        sel_email=unique[sub_opts.index(sel_sub)][0]
                        sub_r=subs[subs["email"]==sel_email].sort_values("submit_time",ascending=False).iloc[0]
                        qs=json.loads(sub_r["questions_json"]) if sub_r.get("questions_json") else []
                        ans=json.loads(sub_r["answers_json"]) if sub_r.get("answers_json") else {}
                        ovr=json.loads(sub_r["overrides_json"]) if sub_r.get("overrides_json") else {}
                        correct,total,pct=compute_score(qs,ans,ovr)
                        pass_m=int(c_df2[c_df2["course_id"]==rev_cid]["pass_mark"].values[0])
                        c1,c2,c3=st.columns(3)
                        with c1: st.metric("Student",sub_r["name"])
                        with c2: st.metric("Score",f"{correct}/{total} ({pct:.1f}%)")
                        with c3: st.metric("Status","✅ Pass" if pct>=pass_m else "❌ Fail")
                        if sub_r.get("corrected_by"):
                            st.info(f"🖊️ Corrected by **{sub_r['corrected_by']}** on {str(sub_r.get('corrected_at',''))[:19]}")
                        st.markdown("---")
                        new_ovr={}
                        for i,q in enumerate(qs):
                            key=f"q_{i}"; s_ans=str(ans.get(key,"*(no answer)*")).strip(); c_ans=str(q["answer"]).strip()
                            auto_ok=s_ans.lower()==c_ans.lower(); ex_ov=ovr.get(key)
                            badge=("🟡 Overridden ✅" if ex_ov is True else "🟡 Overridden ❌" if ex_ov is False
                                   else "✅ Auto-Correct" if auto_ok else "❌ Auto-Wrong")
                            with st.expander(f"Q{i+1}: {badge} — {str(q['question'])[:65]}"):
                                st.markdown(f"**Q:** {q['question']}")
                                if q.get("type")=="mcq": st.markdown(f"**Options:** {' | '.join(q.get('options',[]))}")
                                st.markdown(f"**Correct:** `{c_ans}`")
                                if auto_ok: st.success(f"**Student:** {s_ans}")
                                else: st.error(f"**Student:** {s_ans}")
                                di=(1 if ex_ov is True else 2 if ex_ov is False else 0)
                                ch=st.radio("Mark:",["🤖 Auto","✅ Correct","❌ Wrong"],index=di,key=f"ov_{rev_cid}_{i}",horizontal=True)
                                if ch=="✅ Correct": new_ovr[key]=True
                                elif ch=="❌ Wrong": new_ovr[key]=False
                        st.markdown("---")
                        pc,pt,pp=compute_score(qs,ans,new_ovr)
                        c1,c2=st.columns(2)
                        with c1: st.info(f"📊 New: **{pc}/{pt} ({pp:.1f}%)** — {'✅ Pass' if pp>=pass_m else '❌ Fail'}")
                        with c2:
                            AE,_=get_admin_credentials()
                            if st.button("💾 Save Corrections",use_container_width=True,type="primary"):
                                sub_id=int(sub_r["id"])
                                db_update("submissions",{"id":sub_id},{"overrides_json":json.dumps(new_ovr),
                                    "corrected_by":AE,"corrected_at":datetime.now().isoformat()})
                                res_r=db().table("results").select("id").eq("email",sel_email).eq("course_id",rev_cid).order("submit_time",desc=True).limit(1).execute()
                                if res_r.data:
                                    db_update("results",{"id":res_r.data[0]["id"]},{"score":pc,"percentage":pp})
                                st.success(f"✅ Saved! {pc}/{pt} ({pp:.1f}%)"); st.rerun()

    with tab_leader:
        st.subheader("🏆 Leaderboard")
        with st.spinner("Loading..."): lb_cdf=db_all("courses")
        if lb_cdf.empty: st.info("No courses.")
        else:
            lb_c=st.selectbox("Course:",[f"{r['course_name']} ({r['course_id']})" for _,r in lb_cdf.iterrows()],key="lb_c")
            lb_cid=lb_c.split("(")[-1].rstrip(")")
            show_top=st.slider("Show top:",5,50,10,key="lb_top")
            with st.spinner("Loading..."): lb_all=db_all("results",{"course_id":lb_cid})
            if lb_all.empty: st.info("No results yet.")
            else:
                lb_all["percentage"]=pd.to_numeric(lb_all["percentage"],errors="coerce")
                lb_df=lb_all.sort_values("percentage",ascending=False).drop_duplicates("email",keep="first")
                lb_df=lb_df[["name","email","score","total","percentage","attempt_num"]].head(show_top).reset_index(drop=True)
                lb_df.index+=1; lb_df.index.name="Rank"
                pass_m=int(lb_cdf[lb_cdf["course_id"]==lb_cid]["pass_mark"].values[0])
                medals={1:"🥇",2:"🥈",3:"🥉"}; css={1:"lb-gold",2:"lb-silver",3:"lb-bronze"}
                for rank,row in lb_df.iterrows():
                    pct=float(row["percentage"]); medal=medals.get(rank,f"#{rank}"); cls=css.get(rank,"lb-row")
                    st.markdown(f'<div class="lb-row {cls}"><div class="lb-rank">{medal}</div>'
                                f'<div class="lb-name">{row["name"]}</div>'
                                f'<div style="color:#64748b;font-size:0.85rem;margin-right:1rem;">{row["email"]}</div>'
                                f'<div class="lb-score">{pct:.1f}% {"✅" if pct>=pass_m else "❌"}</div></div>',
                                unsafe_allow_html=True)
                st.markdown("---")
                st.download_button("⬇️ Export Excel",build_excel(lb_df.reset_index()),
                    f"leaderboard_{lb_cid}.xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    with tab_devices:
        st.subheader("Device Management")
        c1,c2=st.columns(2)
        with c1:
            st.markdown("**Block a Device**")
            dblk=st.text_input("Device ID",key="blk_d"); drsn=st.text_area("Reason",height=70,key="blk_r"); dem=st.text_input("Email",key="blk_e")
            if st.button("🚫 Block"):
                if dblk.strip():
                    db_insert("blocked_devices",{"device_id":dblk.strip(),"reason":drsn,"email":dem,"blocked_at":datetime.now().isoformat()})
                    st.success("Blocked."); st.rerun()
        with c2:
            st.markdown("**Unblock a Device**")
            with st.spinner("..."): blk_df=db_all("blocked_devices")
            if not blk_df.empty:
                active=blk_df[blk_df["unblocked_at"].isna() | (blk_df["unblocked_at"].astype(str)=="")]
                if not active.empty:
                    dunblk=st.selectbox("Select:",active["device_id"].tolist())
                    if st.button("✅ Unblock"):
                        db_update("blocked_devices",{"device_id":dunblk},{"unblocked_at":datetime.now().isoformat()})
                        st.success("Unblocked."); st.rerun()
                else: st.info("None blocked.")
            else: st.info("None blocked.")

    with tab_analytics:
        st.subheader("📈 Analytics")
        with st.spinner("..."): all_res=db_all("results")
        if all_res.empty: st.info("No data yet.")
        else:
            all_res["percentage"]=pd.to_numeric(all_res["percentage"],errors="coerce")
            c1,c2,c3,c4=st.columns(4)
            with c1: st.metric("Submissions",len(all_res))
            with c2: st.metric("Avg Score",f"{all_res['percentage'].mean():.1f}%")
            with c3: st.metric("Pass Rate",f"{(all_res['percentage']>=PASS_MARK).mean()*100:.1f}%")
            with c4: st.metric("Top Score",f"{all_res['percentage'].max():.1f}%")
            if "course_name" in all_res.columns:
                st.markdown("---"); st.subheader("Per-Course")
                summary=(all_res.groupby("course_name")["percentage"].agg(["count","mean","max"])
                         .rename(columns={"count":"Submissions","mean":"Avg %","max":"Top %"}).round(1))
                st.dataframe(summary,use_container_width=True)
            st.markdown("---"); st.subheader("Score Distribution")
            st.bar_chart(all_res["percentage"].value_counts().sort_index())

    st.markdown("---")
    if st.button("🚪 Logout"):
        st.session_state.admin_auth=False; st.session_state.show_admin_login=False
        st.session_state.page="login"; st.rerun()
