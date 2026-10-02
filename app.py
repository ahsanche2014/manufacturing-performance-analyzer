
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from io import BytesIO

st.set_page_config(page_title="Manufacturing Performance Analyzer", page_icon="🏭", layout="wide")

STANDARD = {
    "Date": ["date","production date","prod date"], "Plant": ["plant","factory","building"],
    "Machine": ["machine","machine no","machine name","mc"], "Shift": ["shift"],
    "Item": ["item","item code","product","sku","wip"],
    "Planned Min": ["planned min","available time","planned time","loading time"],
    "Downtime Min": ["downtime min","stop time","downtime","breakdown min"],
    "Downtime Reason": ["downtime reason","stop reason","loss reason","breakdown reason","reason"],
    "Ideal Cycle Sec": ["ideal cycle sec","std cycle","standard cycle","cycle time"],
    "Total Qty": ["total qty","production qty","actual qty","output"],
    "Good Qty": ["good qty","ok qty","accepted qty"], "Reject Qty": ["reject qty","ng qty","rejection qty","scrap qty"],
    "Energy kWh": ["energy kwh","power kwh","kwh"], "Material kg": ["material kg","material consumption","resin kg"],
}
REQUIRED = ["Machine","Planned Min","Downtime Min","Ideal Cycle Sec","Total Qty"]

def norm(x):
    import re
    x=str(x).strip().lower().replace("_"," ").replace("-"," ")
    x=re.sub(r"[^a-z0-9 ]+"," ",x)
    return " ".join(x.split())
def auto_map(cols):
    ncols={norm(c):c for c in cols}; result={}
    for std,aliases in STANDARD.items():
        result[std]=next((ncols[a] for a in [norm(std)]+[norm(x) for x in aliases] if a in ncols),None)
    return result
def demo():
    rng=np.random.default_rng(42); rows=[]; dates=pd.date_range("2026-09-01",periods=30)
    machines=[f"IMM-{i:02d}" for i in range(1,7)]; items=["Faucet Body-A","Handle-B","Rosette-C","Connector-D"]
    for d,dt in enumerate(dates):
        for j,m in enumerate(machines):
            planned=720; down=int(rng.integers(25,151)); ideal=int(rng.choice([22,26,30,34,38])); run=planned-down
            total=max(1,int(round((run*60/ideal)*rng.uniform(.76,.96)))); reject=int(round(total*rng.uniform(.012,.075)))
            rows.append([dt,"Plant-A" if j%2==0 else "Plant-B",m,"A" if (d+j)%2==0 else "B",items[(d+j)%4],
                         planned,down,ideal,total,total-reject,reject,round(total*rng.uniform(.11,.18),1),round(total*rng.uniform(.055,.09),1)])
    return pd.DataFrame(rows,columns=["Date","Plant","Machine","Shift","Item","Planned Min","Downtime Min","Ideal Cycle Sec","Total Qty","Good Qty","Reject Qty","Energy kWh","Material kg"])
def canonicalize(df,mapping):
    out=pd.DataFrame()
    for std,source in mapping.items():
        if source and source in df.columns: out[std]=df[source]
    if "Good Qty" not in out and {"Total Qty","Reject Qty"}.issubset(out.columns): out["Good Qty"]=pd.to_numeric(out["Total Qty"],errors="coerce")-pd.to_numeric(out["Reject Qty"],errors="coerce")
    if "Reject Qty" not in out and {"Total Qty","Good Qty"}.issubset(out.columns): out["Reject Qty"]=pd.to_numeric(out["Total Qty"],errors="coerce")-pd.to_numeric(out["Good Qty"],errors="coerce")
    if "Good Qty" not in out and "Total Qty" in out: out["Good Qty"]=pd.to_numeric(out["Total Qty"],errors="coerce"); out["Reject Qty"]=0
    for c in ["Planned Min","Downtime Min","Ideal Cycle Sec","Total Qty","Good Qty","Reject Qty","Energy kWh","Material kg"]:
        if c in out: out[c]=pd.to_numeric(out[c],errors="coerce")
    if "Date" in out: out["Date"]=pd.to_datetime(out["Date"],errors="coerce")
    return out.dropna(subset=[c for c in REQUIRED if c in out.columns])
def analyze(d):
    d=d.copy(); d["Run Min"]=(d["Planned Min"]-d["Downtime Min"]).clip(lower=0)
    d["Availability"]=np.where(d["Planned Min"]>0,d["Run Min"]/d["Planned Min"],0)
    d["Performance"]=np.where(d["Run Min"]>0,(d["Ideal Cycle Sec"]*d["Total Qty"])/(d["Run Min"]*60),0).clip(0,1.25)
    d["Quality"]=np.where(d["Total Qty"]>0,d["Good Qty"]/d["Total Qty"],0); d["OEE"]=d["Availability"]*d["Performance"]*d["Quality"]; return d
def grouped(d,by):
    g=d.groupby(by,dropna=False).agg(Planned_Min=("Planned Min","sum"),Downtime_Min=("Downtime Min","sum"),Total_Qty=("Total Qty","sum"),Good_Qty=("Good Qty","sum"),Reject_Qty=("Reject Qty","sum")).reset_index()
    run=g["Planned_Min"]-g["Downtime_Min"]; w=d.assign(ideal_output_sec=d["Ideal Cycle Sec"]*d["Total Qty"]).groupby(by,dropna=False)["ideal_output_sec"].sum().reset_index(); g=g.merge(w,on=by,how="left")
    g["Availability"]=np.where(g["Planned_Min"]>0,run/g["Planned_Min"],0); g["Performance"]=np.where(run>0,g["ideal_output_sec"]/(run*60),0).clip(0,1.25)
    g["Quality"]=np.where(g["Total_Qty"]>0,g["Good_Qty"]/g["Total_Qty"],0); g["OEE"]=g["Availability"]*g["Performance"]*g["Quality"]; return g
def loss_engine(d):
    x=d.copy()
    x["Ideal Rate ppm"]=np.where(x["Ideal Cycle Sec"]>0,60/x["Ideal Cycle Sec"],0)
    x["Availability Lost Qty"]=x["Downtime Min"].clip(lower=0)*x["Ideal Rate ppm"]
    x["Performance Lost Qty"]=np.maximum(0,(x["Run Min"]*x["Ideal Rate ppm"])-x["Total Qty"])
    x["Quality Lost Qty"]=x["Reject Qty"].clip(lower=0)
    x["Total Opportunity Qty"]=x["Availability Lost Qty"]+x["Performance Lost Qty"]+x["Quality Lost Qty"]
    return x
def loss_summary(d,by):
    x=loss_engine(d)
    return x.groupby(by,dropna=False).agg(Availability_Loss=("Availability Lost Qty","sum"),Performance_Loss=("Performance Lost Qty","sum"),Quality_Loss=("Quality Lost Qty","sum"),Total_Opportunity=("Total Opportunity Qty","sum"),Downtime_Min=("Downtime Min","sum"),Reject_Qty=("Reject Qty","sum")).reset_index().sort_values("Total_Opportunity",ascending=False)
def overall(d):
    planned=d["Planned Min"].sum(); run=planned-d["Downtime Min"].sum(); total=d["Total Qty"].sum(); good=d["Good Qty"].sum()
    a=run/planned if planned else 0; p=(d["Ideal Cycle Sec"]*d["Total Qty"]).sum()/(run*60) if run else 0; q=good/total if total else 0; p=min(p,1.25); return a,p,q,a*p*q
def insight(m):
    worst=m.sort_values("OEE").iloc[0]; down=m.sort_values("Downtime_Min",ascending=False).iloc[0]
    rej=m.assign(Reject_Rate=np.where(m.Total_Qty>0,m.Reject_Qty/m.Total_Qty,0)).sort_values("Reject_Rate",ascending=False).iloc[0]
    return [f"Priority machine: {worst['Machine']} - OEE {worst['OEE']:.1%}.",f"Highest downtime: {down['Machine']} - {down['Downtime_Min']:,.0f} min.",f"Highest rejection exposure: {rej['Machine']} - {rej['Reject_Rate']:.1%}.","Next action: validate top downtime and rejection causes at Gemba, assign owner, target date and quantified recovery opportunity."]

st.markdown("""<style>
#MainMenu,footer{visibility:hidden}.block-container{padding:1.1rem 2rem 3rem;max-width:1500px}
.stApp{background:linear-gradient(180deg,#f4f7fb 0%,#eef3f8 100%);color:#15253b}
h1{font-size:2.05rem!important;font-weight:800!important;letter-spacing:-.04em;color:#102a43!important} h2,h3{color:#17365d!important;font-weight:750!important}
[data-testid="stSidebar"]{background:#0d2742}[data-testid="stSidebar"] *{color:#eef6ff}
div[data-testid="stMetric"]{background:linear-gradient(145deg,#fff,#f7faff);border:1px solid #dce6f0;padding:17px 18px;border-radius:16px;box-shadow:0 6px 18px rgba(21,53,83,.07)}
div[data-testid="stMetricLabel"]{font-size:.78rem;font-weight:700;text-transform:uppercase;letter-spacing:.055em;color:#61758a}
div[data-testid="stMetricValue"]{font-size:1.65rem;font-weight:800;color:#102a43}
[data-testid="stPlotlyChart"]{background:#fff;border:1px solid #dce6f0;border-radius:18px;padding:8px;box-shadow:0 6px 18px rgba(21,53,83,.055)}
[data-testid="stDataFrame"]{border:1px solid #dce6f0;border-radius:14px;overflow:hidden}
div.stAlert{border-radius:14px}.stDownloadButton button{border-radius:12px;font-weight:700}
@media(max-width:700px){.block-container{padding:.8rem .8rem 2rem}h1{font-size:1.65rem!important}div[data-testid="stMetric"]{padding:12px}}
</style>""",unsafe_allow_html=True)
st.markdown("### MANUFACTURING INTELLIGENCE"); st.title("Performance Command Center"); st.caption("Production performance • loss intelligence • recovery focus")
with st.sidebar:
    st.header("1. Data Source"); source=st.radio("Choose input",["Demo data","Upload Excel / CSV"]); raw=None
    if source=="Demo data": raw=demo()
    else:
        f=st.file_uploader("Upload .xlsx, .xls or .csv",type=["xlsx","xls","csv"])
        if f:
            try: raw=pd.read_csv(f) if f.name.lower().endswith(".csv") else pd.read_excel(f)
            except Exception as e: st.error(f"Could not read file: {e}")
    st.divider(); st.caption("Uploaded data is processed in the running app session. This MVP does not implement permanent database storage.")
if raw is None: st.info("Upload a production file from the sidebar, or select Demo data."); st.stop()
st.subheader("2. Column Mapping"); suggested=auto_map(raw.columns); mapping={}; cols=["— Not mapped —"]+list(raw.columns)
with st.expander("Review / change mapping",expanded=(source!="Demo data")):
    c1,c2,c3=st.columns(3)
    for i,std in enumerate(STANDARD):
        default=suggested.get(std); idx=cols.index(default) if default in cols else 0
        with [c1,c2,c3][i%3]:
            sel=st.selectbox(std,cols,index=idx,key=f"map_{std}"); mapping[std]=None if sel=="— Not mapped —" else sel
missing=[x for x in REQUIRED if not mapping.get(x)]
if missing: st.error("Required fields not mapped: "+", ".join(missing)); st.stop()
d=analyze(canonicalize(raw,mapping))
if d.empty: st.error("No valid rows remained after mapping/cleaning."); st.stop()
st.subheader("3. Analyze"); f1,f2,f3=st.columns(3)
with f1: machines=sorted(d["Machine"].dropna().astype(str).unique()); selected_m=st.multiselect("Machine",machines,default=machines)
with f2:
    if "Shift" in d: shifts=sorted(d["Shift"].dropna().astype(str).unique()); selected_s=st.multiselect("Shift",shifts,default=shifts)
    else: selected_s=[]
with f3:
    if "Item" in d: items=sorted(d["Item"].dropna().astype(str).unique()); selected_i=st.multiselect("Item",items,default=items)
    else: selected_i=[]
view=d[d["Machine"].astype(str).isin(selected_m)]
if "Shift" in view and selected_s: view=view[view["Shift"].astype(str).isin(selected_s)]
if "Item" in view and selected_i: view=view[view["Item"].astype(str).isin(selected_i)]
if view.empty: st.warning("Current filters return no data."); st.stop()
a,p,q,o=overall(view); k1,k2,k3,k4,k5=st.columns(5); k1.metric("OEE",f"{o:.1%}"); k2.metric("Availability",f"{a:.1%}"); k3.metric("Performance",f"{p:.1%}"); k4.metric("Quality",f"{q:.1%}"); k5.metric("Reject Qty",f"{view['Reject Qty'].sum():,.0f}")
machine=grouped(view,"Machine")
loss_machine=loss_summary(view,"Machine")
st.markdown("### Loss Intelligence")
li1,li2,li3,li4=st.columns(4)
li1.metric("Availability Loss",f"{loss_machine['Availability_Loss'].sum():,.0f} pcs")
li2.metric("Performance Loss",f"{loss_machine['Performance_Loss'].sum():,.0f} pcs")
li3.metric("Quality Loss",f"{loss_machine['Quality_Loss'].sum():,.0f} pcs")
li4.metric("Total Opportunity",f"{loss_machine['Total_Opportunity'].sum():,.0f} pcs")
loss_totals={"Availability":loss_machine["Availability_Loss"].sum(),"Performance":loss_machine["Performance_Loss"].sum(),"Quality":loss_machine["Quality_Loss"].sum()}
priority=max(loss_totals,key=loss_totals.get)
st.info(f"Priority loss pillar: {priority} - largest quantified production opportunity in the selected data.")
lc1,lc2=st.columns([1.2,1])
with lc1: st.plotly_chart(px.bar(loss_machine,x="Machine",y="Total_Opportunity",title="Machine Loss Ranking - Opportunity Qty",text_auto=".0f"),use_container_width=True)
with lc2:
    loss_long=pd.DataFrame({"Loss Pillar":list(loss_totals.keys()),"Opportunity Qty":list(loss_totals.values())}).sort_values("Opportunity Qty",ascending=False)
    st.plotly_chart(px.bar(loss_long,x="Loss Pillar",y="Opportunity Qty",title="A/P/Q Loss Decomposition",text_auto=".0f"),use_container_width=True)
if "Downtime Reason" in view and view["Downtime Reason"].notna().any():
    reason=view.groupby("Downtime Reason",dropna=False)["Downtime Min"].sum().reset_index().sort_values("Downtime Min",ascending=False)
    st.markdown("#### Downtime Pareto")
    st.plotly_chart(px.bar(reason.head(15),x="Downtime Reason",y="Downtime Min",title="Top Downtime Reasons",text_auto=".0f"),use_container_width=True)
if "Item" in view:
    reject_item=view.groupby("Item",dropna=False).agg(Reject_Qty=("Reject Qty","sum"),Total_Qty=("Total Qty","sum")).reset_index()
    reject_item["Reject Rate"]=np.where(reject_item["Total_Qty"]>0,reject_item["Reject_Qty"]/reject_item["Total_Qty"],0)
    st.markdown("#### Rejection Pareto by Item")
    st.plotly_chart(px.bar(reject_item.sort_values("Reject_Qty",ascending=False).head(15),x="Item",y="Reject_Qty",title="Top Rejection Exposure",text_auto=".0f"),use_container_width=True)
left,right=st.columns([1.25,1])
with left:
    fig=px.bar(machine.sort_values("OEE"),x="Machine",y="OEE",title="Machine-wise OEE",text_auto=".1%"); fig.update_yaxes(tickformat=".0%",range=[0,max(1,float(machine.OEE.max()*1.15))]); st.plotly_chart(fig,use_container_width=True)
with right: st.plotly_chart(px.bar(machine.sort_values("Downtime_Min",ascending=False),x="Machine",y="Downtime_Min",title="Downtime Exposure (min)",text_auto=".0f"),use_container_width=True)
st.markdown("### Management Diagnosis")
for x in insight(machine): st.write("• "+x)
if "Item" in view:
    item=grouped(view,"Item"); st.markdown("### Item Loss View"); st.dataframe(item[["Item","Total_Qty","Reject_Qty","Availability","Performance","Quality","OEE"]].sort_values("OEE").style.format({"Availability":"{:.1%}","Performance":"{:.1%}","Quality":"{:.1%}","OEE":"{:.1%}"}),use_container_width=True,hide_index=True)
st.markdown("### Machine Detail"); display=machine[["Machine","Planned_Min","Downtime_Min","Total_Qty","Good_Qty","Reject_Qty","Availability","Performance","Quality","OEE"]].copy()
st.dataframe(display.style.format({"Availability":"{:.1%}","Performance":"{:.1%}","Quality":"{:.1%}","OEE":"{:.1%}"}),use_container_width=True,hide_index=True)
def make_report():
    bio=BytesIO()
    with pd.ExcelWriter(bio,engine="openpyxl") as writer: view.to_excel(writer,index=False,sheet_name="Analyzed_Data"); machine.to_excel(writer,index=False,sheet_name="Machine_Summary"); loss_machine.to_excel(writer,index=False,sheet_name="Loss_Intelligence")
    return bio.getvalue()
st.download_button("Download analyzed Excel report",data=make_report(),file_name="manufacturing_performance_analysis.xlsx",mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
st.caption("v1.3 | Performance Command Center + Loss Intelligence | OEE = Availability × Performance × Quality. Validate ideal-cycle and planned-time definitions against each client's production standard before commercial use.")
