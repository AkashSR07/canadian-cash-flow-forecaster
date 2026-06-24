import numpy as np
import pandas as pd
import plotly.express as px
import altair as alt
import streamlit as st
from datetime import timedelta
from io import BytesIO


st.set_page_config(
    page_title="Canadian Cash Flow Forecaster",
    page_icon=":bar_chart:",
    layout="wide",
    initial_sidebar_state="expanded",
)


DEFAULT_INVOICE_CSV = """date,customer,invoice_amount,days_to_pay,status
2026-05-01,Maple Foods,8500,18,Paid
2026-05-04,North Star Retail,6200,35,Pending
2026-05-09,Harbour Clinic,4800,21,Paid
2026-05-14,True North Logistics,9100,42,Pending
2026-05-22,Urban Build Co,5700,27,Paid
2026-05-28,Red River Services,7600,31,Pending
"""

DEFAULT_EXPENSE_CSV = """date,vendor,expense_amount,category,recurring
2026-05-02,Office Supply Co,1200,Operations,Yes
2026-05-07,Cloud Hosting Inc,680,Technology,Yes
2026-05-12,Payroll,18500,Payroll,Yes
2026-05-18,Delivery Fuel,940,Transport,Yes
2026-05-24,Insurance Partner,2100,Fixed,Yes
2026-05-29,One-time Repair,1400,Maintenance,No
"""


def load_css() -> None:
    st.markdown(
        """
        <style>
            .main .block-container { padding-top: 1.6rem; padding-bottom: 2rem; max-width: 1300px; }
            .hero {
                padding: 1.5rem 1.7rem;
                border-radius: 16px;
                background: linear-gradient(135deg, #0f172a 0%, #2563eb 100%);
                color: white;
                margin-bottom: 1.2rem;
            }
            .hero h1 { margin: 0; font-size: 2.2rem; }
            .hero p { margin: .5rem 0 0; color: #dbeafe; font-size: 1rem; }
            .soft-card {
                background: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 12px;
                padding: 1rem 1.05rem;
                box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05);
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def parse_csv_upload(uploaded_file, default_csv: str) -> pd.DataFrame:
    if uploaded_file is None:
        return pd.read_csv(BytesIO(default_csv.encode("utf-8")))
    return pd.read_csv(uploaded_file)


def clean_dates(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date")


def infer_business_profile(invoice_df: pd.DataFrame, expense_df: pd.DataFrame) -> dict:
    avg_invoice = float(invoice_df["invoice_amount"].mean())
    total_monthly_expense = float(expense_df["expense_amount"].sum())
    avg_days_to_pay = float(invoice_df["days_to_pay"].mean())
    pending_ratio = float((invoice_df["status"].astype(str).str.lower() == "pending").mean())
    recurring_ratio = float((expense_df["recurring"].astype(str).str.lower() == "yes").mean())

    stage = "Growth"
    if avg_invoice < 5000 and total_monthly_expense < 15000:
        stage = "Early"
    elif avg_invoice > 8000 or total_monthly_expense > 30000:
        stage = "Scaling"

    risk_score = (
        (pending_ratio * 35)
        + (min(avg_days_to_pay, 60) / 60 * 25)
        + (min(total_monthly_expense / max(avg_invoice, 1), 3) / 3 * 20)
        + (recurring_ratio * 20)
    )

    return {
        "avg_invoice": avg_invoice,
        "total_monthly_expense": total_monthly_expense,
        "avg_days_to_pay": avg_days_to_pay,
        "pending_ratio": pending_ratio,
        "recurring_ratio": recurring_ratio,
        "stage": stage,
        "risk_score": round(min(risk_score, 100), 1),
    }


def build_forecast(invoice_df: pd.DataFrame, expense_df: pd.DataFrame, months: int, conservative: float, collection_speed: float) -> tuple[pd.DataFrame, dict, list[str]]:
    invoice_df = clean_dates(invoice_df)
    expense_df = clean_dates(expense_df)

    start_date = min(invoice_df["date"].min(), expense_df["date"].min())
    periods = months * 30
    dates = pd.date_range(start=start_date, periods=periods, freq="D")

    daily_inflow = np.zeros(len(dates))
    daily_outflow = np.zeros(len(dates))

    for _, row in invoice_df.iterrows():
        due_date = row["date"] + timedelta(days=int(row["days_to_pay"] * collection_speed))
        idx = np.searchsorted(dates.values, np.datetime64(due_date))
        if idx < len(dates):
            daily_inflow[idx] += float(row["invoice_amount"]) * conservative

    for _, row in expense_df.iterrows():
        idx = np.searchsorted(dates.values, np.datetime64(row["date"]))
        if idx < len(dates):
            amount = float(row["expense_amount"])
            daily_outflow[idx] += amount
            if str(row["recurring"]).lower() == "yes":
                for extra in range(30, len(dates) - idx, 30):
                    daily_outflow[idx + extra] += amount

    cash = []
    running = 0.0
    initial_cash = 25000.0
    low_point = initial_cash
    low_point_date = dates[0]

    for i, current_date in enumerate(dates):
        running += daily_inflow[i] - daily_outflow[i]
        balance = initial_cash + running
        cash.append(balance)
        if balance < low_point:
            low_point = balance
            low_point_date = current_date

    timeline = pd.DataFrame(
        {
            "date": dates,
            "inflow": daily_inflow,
            "outflow": daily_outflow,
            "net_flow": daily_inflow - daily_outflow,
            "cash_balance": cash,
        }
    )
    monthly = timeline.set_index("date").resample("M").sum(numeric_only=True).reset_index()
    summary = {
        "projected_end_cash": float(timeline["cash_balance"].iloc[-1]),
        "min_cash": float(low_point),
        "min_cash_date": pd.to_datetime(low_point_date),
        "avg_monthly_inflow": float(monthly["inflow"].mean()),
        "avg_monthly_outflow": float(monthly["outflow"].mean()),
    }

    alerts = []
    if summary["min_cash"] < 10000:
        alerts.append("Cash buffer drops below a safe small-business threshold in the forecast window.")
    if summary["projected_end_cash"] < initial_cash:
        alerts.append("Projected end cash is lower than the opening balance, so collections or expenses need attention.")
    if expense_df["category"].astype(str).str.lower().eq("payroll").any():
        alerts.append("Payroll is a major fixed expense, so timing of collections matters more than usual.")

    return timeline, summary, alerts


def make_recommendations(profile: dict, summary: dict, alerts: list[str]) -> list[str]:
    recs = []
    if profile["pending_ratio"] > 0.35:
        recs.append("Tighten invoice follow-up with automated reminders for overdue customers.")
    if profile["avg_days_to_pay"] > 30:
        recs.append("Offer early-payment incentives or deposits for larger jobs to reduce collection delays.")
    if profile["risk_score"] > 60:
        recs.append("Build a reserve buffer and cut discretionary spend until the next cash cycle stabilizes.")
    if summary["min_cash"] < 15000:
        recs.append("Review monthly subscriptions and one-time expenses before committing to new hires or equipment.")
    if profile["recurring_ratio"] > 0.5:
        recs.append("Separate recurring operating costs from variable project costs so owners can see fixed burn clearly.")
    if alerts:
        recs.append("Use the risk alerts section as a weekly operating checklist.")
    return recs or ["The current forecast looks stable. Keep monitoring collections and renew the forecast weekly."]


def render_metric_row(profile: dict, summary: dict) -> None:
    cols = st.columns(4)
    cols[0].metric("Cash at End of Forecast", f"C$ {summary['projected_end_cash']:,.0f}")
    cols[1].metric("Lowest Projected Cash", f"C$ {summary['min_cash']:,.0f}")
    cols[2].metric("Risk Score", f"{profile['risk_score']}/100")
    cols[3].metric("Business Stage", profile["stage"])


def render_alerts(alerts: list[str], recommendations: list[str]) -> None:
    left, right = st.columns(2)
    with left:
        st.subheader("Risk Alerts")
        if alerts:
            for item in alerts:
                st.error(item)
        else:
            st.success("No immediate cash pressure detected in this forecast window.")
    with right:
        st.subheader("Recommended Actions")
        for item in recommendations:
            st.write(f"- {item}")


def render_charts(timeline: pd.DataFrame) -> None:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Cash Balance Forecast")
        chart = (
            alt.Chart(timeline)
            .mark_line(color="#2563eb", strokeWidth=3)
            .encode(
                x=alt.X("date:T", title="Date"),
                y=alt.Y("cash_balance:Q", title="Cash Balance (CAD)"),
                tooltip=["date:T", "cash_balance:Q", "inflow:Q", "outflow:Q"],
            )
            .interactive()
        )
        st.altair_chart(chart, use_container_width=True)

    with c2:
        st.subheader("Monthly Flow")
        monthly = timeline.set_index("date").resample("M").sum(numeric_only=True).reset_index()
        melted = monthly.melt(id_vars="date", value_vars=["inflow", "outflow"], var_name="type", value_name="amount")
        fig = px.bar(
            melted,
            x="date",
            y="amount",
            color="type",
            barmode="group",
            color_discrete_map={"inflow": "#16a34a", "outflow": "#dc2626"},
        )
        fig.update_layout(height=400, margin=dict(l=10, r=10, t=20, b=10), legend_title_text="")
        st.plotly_chart(fig, use_container_width=True)


def export_forecast_csv(timeline: pd.DataFrame) -> bytes:
    return timeline.to_csv(index=False).encode("utf-8")


def main() -> None:
    load_css()

    st.markdown(
        """
        <div class="hero">
            <h1>Canadian Cash Flow Forecaster</h1>
            <p>Built for small businesses that need clearer visibility into collections, expenses, and short-term cash risk.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.header("Inputs")
        invoice_file = st.file_uploader("Upload invoice CSV", type=["csv"])
        expense_file = st.file_uploader("Upload expense CSV", type=["csv"])
        forecast_months = st.slider("Forecast horizon", 1, 12, 6)
        collections_speed = st.slider("Collection speed multiplier", 0.5, 1.5, 1.0, 0.05)
        conservative_factor = st.slider("Revenue conservatism", 0.7, 1.2, 0.9, 0.05)
        st.caption("Use 1.0 for neutral assumptions. Lower values make the forecast more cautious.")

    st.subheader("Business Snapshot")
    st.write(
        "This tool helps Canadian SMEs estimate cash flow, spot risk early, and make better decisions about hiring, spending, and collections."
    )

    invoice_df = parse_csv_upload(invoice_file, DEFAULT_INVOICE_CSV)
    expense_df = parse_csv_upload(expense_file, DEFAULT_EXPENSE_CSV)

    required_invoice_cols = {"date", "customer", "invoice_amount", "days_to_pay", "status"}
    required_expense_cols = {"date", "vendor", "expense_amount", "category", "recurring"}
    if not required_invoice_cols.issubset(invoice_df.columns) or not required_expense_cols.issubset(expense_df.columns):
        st.error("CSV columns do not match the expected template. Use the sample format shown in the README.")
        return

    profile = infer_business_profile(invoice_df, expense_df)
    timeline, summary, alerts = build_forecast(invoice_df, expense_df, forecast_months, conservative_factor, collections_speed)
    recommendations = make_recommendations(profile, summary, alerts)

    render_metric_row(profile, summary)
    st.progress(min(profile["risk_score"] / 100, 1.0))

    tab_overview, tab_data, tab_forecast, tab_export = st.tabs(["Overview", "Data", "Forecast", "Export"])

    with tab_overview:
        left, right = st.columns(2)
        with left:
            st.subheader("What this business looks like")
            st.markdown(
                f"""
                <div class="soft-card">
                Average invoice value: <strong>C$ {profile['avg_invoice']:,.0f}</strong><br>
                Average days to collect: <strong>{profile['avg_days_to_pay']:.0f}</strong><br>
                Monthly expense base: <strong>C$ {profile['total_monthly_expense']:,.0f}</strong><br>
                Pending invoice ratio: <strong>{profile['pending_ratio']:.0%}</strong>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with right:
            st.subheader("Canada-focused use case")
            st.info("Designed for CAD cash flow, small business planning, and owner-friendly decision support.")
            st.write("- Useful for retail, service, logistics, and early-stage SME operations")
            st.write("- Helps spot short-term liquidity issues before they become urgent")
            st.write("- Good fit for a Canadian business analytics or fintech portfolio")

        render_alerts(alerts, recommendations)

    with tab_data:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Invoice Data")
            st.dataframe(invoice_df, use_container_width=True)
        with c2:
            st.subheader("Expense Data")
            st.dataframe(expense_df, use_container_width=True)

    with tab_forecast:
        render_charts(timeline)

    with tab_export:
        st.subheader("Download Forecast")
        st.download_button(
            "Download forecast CSV",
            data=export_forecast_csv(timeline),
            file_name="cash_flow_forecast.csv",
            mime="text/csv",
            use_container_width=True,
        )
        st.download_button(
            "Download summary text",
            data="\n".join(recommendations + alerts),
            file_name="cash_flow_summary.txt",
            mime="text/plain",
            use_container_width=True,
        )


if __name__ == "__main__":
    main()
