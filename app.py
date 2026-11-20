import json
import os
from datetime import datetime
from io import BytesIO

import pandas as pd
import streamlit as st
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    select,
)

st.set_page_config(
    page_title="Children Data Collection",
    page_icon=":material/child_care:",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
# Set DATABASE_URL to point at your database. Examples:
#   MySQL:      mysql+pymysql://user:password@host:3306/dbname
#   PostgreSQL: postgresql+psycopg2://user:password@host:5432/dbname
# If it is not set, a local SQLite file (children.db) is used.


def get_db_url() -> str:
    url = None
    try:
        if "DATABASE_URL" in st.secrets:
            url = st.secrets["DATABASE_URL"]
    except Exception:
        pass
    if not url:
        url = os.getenv("DATABASE_URL", "sqlite:///children.db")

    # Always use the psycopg (v3) driver for Postgres, whatever prefix was pasted
    for prefix in ("postgresql+psycopg2://", "postgresql://", "postgres://"):
        if url.startswith(prefix):
            url = "postgresql+psycopg://" + url[len(prefix):]
            break
    return url


metadata = MetaData()

children = Table(
    "children",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("parent_name", String(150), nullable=False),
    Column("child_name", String(150), nullable=False),
    Column("age", Integer, nullable=False),
    Column("grade", String(50), nullable=False),
    Column("school", String(200), nullable=False),
    Column("extra", Text, nullable=True),  # JSON for custom fields
    Column("created_at", DateTime, default=datetime.now),
)

custom_fields = Table(
    "custom_fields",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(100), nullable=False, unique=True),
    Column("field_type", String(20), nullable=False),
    Column("options", Text, nullable=True),
    Column("required", Integer, default=0),
)


@st.cache_resource
def get_engine():
    engine = create_engine(get_db_url(), pool_pre_ping=True)
    metadata.create_all(engine)
    return engine


engine = get_engine()

GRADES = (
    ["PP1", "PP2"]
    + [f"Grade {i}" for i in range(1, 13)]
    + ["Other"]
)

FIELD_TYPES = ["Text", "Number", "Date", "Dropdown"]

# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------


def load_custom_fields():
    with engine.connect() as conn:
        return conn.execute(select(custom_fields).order_by(custom_fields.c.id)).mappings().all()


def load_children_df() -> pd.DataFrame:
    with engine.connect() as conn:
        rows = conn.execute(select(children).order_by(children.c.id.desc())).mappings().all()

    records = []
    for r in rows:
        rec = {
            "ID": r["id"],
            "Parent name": r["parent_name"],
            "Child name": r["child_name"],
            "Age": r["age"],
            "Grade": r["grade"],
            "School": r["school"],
        }
        try:
            extra = json.loads(r["extra"]) if r["extra"] else {}
        except json.JSONDecodeError:
            extra = {}
        rec.update(extra)
        rec["Date added"] = r["created_at"].strftime("%Y-%m-%d %H:%M") if r["created_at"] else ""
        records.append(rec)

    base_cols = ["ID", "Parent name", "Child name", "Age", "Grade", "School", "Date added"]
    df = pd.DataFrame(records)
    if df.empty:
        return pd.DataFrame(columns=base_cols)
    return df


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Children")
        ws = writer.sheets["Children"]
        for idx, col in enumerate(df.columns, start=1):
            longest = max([len(str(col))] + [len(str(v)) for v in df[col].tolist()])
            ws.column_dimensions[ws.cell(row=1, column=idx).column_letter].width = min(longest + 3, 45)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    .block-container { padding-top: 2rem; max-width: 1100px; }
    .app-title { display: flex; align-items: center; gap: 12px; margin-bottom: 0.25rem; }
    .app-title h1 { margin: 0; font-size: 1.75rem; font-weight: 600; }
    .app-sub { opacity: 0.7; margin-bottom: 1.25rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Lucide "users" icon, inline so it follows the theme colour
LUCIDE_USERS = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="30" height="30" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>'
    '<circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/>'
    '<path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>'
)

st.markdown(
    f'<div class="app-title">{LUCIDE_USERS}<h1>Children Data Collection</h1></div>'
    '<div class="app-sub">Record parent and child details, then export them to Excel.</div>',
    unsafe_allow_html=True,
)

fields = load_custom_fields()

tab_add, tab_records, tab_fields = st.tabs(
    [
        ":material/person_add: Add child",
        ":material/table_view: Records",
        ":material/tune: Form fields",
    ]
)

# ---------------------------------------------------------------------------
# Tab 1: Add child
# ---------------------------------------------------------------------------
with tab_add:
    with st.form("child_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        parent_name = c1.text_input("Parent name", placeholder="e.g. Jane Wanjiru")
        child_name = c2.text_input("Child name", placeholder="e.g. Brian Mwangi")

        c3, c4 = st.columns(2)
        age = c3.number_input("Age", min_value=0, max_value=25, value=None, step=1, placeholder="Enter age")
        grade = c4.selectbox("Grade", GRADES, index=None, placeholder="Select grade")

        school = st.text_input("School", placeholder="e.g. Nairobi Primary School")

        extra_values = {}
        if fields:
            st.markdown("**Additional details**")
        for f in fields:
            label = f["name"] + (" *" if f["required"] else "")
            key = f"cf_{f['id']}"
            if f["field_type"] == "Text":
                extra_values[f["name"]] = st.text_input(label, key=key)
            elif f["field_type"] == "Number":
                extra_values[f["name"]] = st.number_input(label, value=None, key=key)
            elif f["field_type"] == "Date":
                extra_values[f["name"]] = st.date_input(label, value=None, key=key)
            elif f["field_type"] == "Dropdown":
                opts = [o.strip() for o in (f["options"] or "").split(",") if o.strip()]
                extra_values[f["name"]] = st.selectbox(label, opts, index=None, key=key)

        submitted = st.form_submit_button("Save record", icon=":material/save:", type="primary")

    if submitted:
        errors = []
        if not parent_name.strip():
            errors.append("Parent name is required.")
        if not child_name.strip():
            errors.append("Child name is required.")
        if age is None:
            errors.append("Age is required.")
        if grade is None:
            errors.append("Grade is required.")
        if not school.strip():
            errors.append("School is required.")
        for f in fields:
            val = extra_values.get(f["name"])
            if f["required"] and (val is None or str(val).strip() == ""):
                errors.append(f"{f['name']} is required.")

        if errors:
            for e in errors:
                st.error(e, icon=":material/error:")
        else:
            clean_extra = {}
            for k, v in extra_values.items():
                if v is None or str(v).strip() == "":
                    clean_extra[k] = ""
                elif hasattr(v, "isoformat"):
                    clean_extra[k] = v.isoformat()
                else:
                    clean_extra[k] = v

            with engine.begin() as conn:
                conn.execute(
                    children.insert().values(
                        parent_name=parent_name.strip(),
                        child_name=child_name.strip(),
                        age=int(age),
                        grade=grade,
                        school=school.strip(),
                        extra=json.dumps(clean_extra),
                        created_at=datetime.now(),
                    )
                )
            st.success("Record saved.", icon=":material/check_circle:")

# ---------------------------------------------------------------------------
# Tab 2: Records
# ---------------------------------------------------------------------------
with tab_records:
    df = load_children_df()

    m1, m2, m3 = st.columns(3)
    m1.metric("Children", len(df))
    m2.metric("Parents", df["Parent name"].nunique() if not df.empty else 0)
    m3.metric("Schools", df["School"].nunique() if not df.empty else 0)

    f1, f2 = st.columns([2, 1])
    search = f1.text_input("Search", placeholder="Search by parent, child or school", icon=":material/search:")
    school_filter = f2.selectbox(
        "School",
        ["All schools"] + (sorted(df["School"].dropna().unique().tolist()) if not df.empty else []),
    )

    view = df.copy()
    if not view.empty:
        if search:
            mask = view.astype(str).apply(lambda col: col.str.contains(search, case=False, na=False)).any(axis=1)
            view = view[mask]
        if school_filter != "All schools":
            view = view[view["School"] == school_filter]

    st.dataframe(view, use_container_width=True, hide_index=True)

    d1, d2 = st.columns([1, 1])
    with d1:
        st.download_button(
            "Download as Excel",
            data=to_excel_bytes(view if not view.empty else df),
            file_name=f"children_data_{datetime.now():%Y%m%d_%H%M}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            icon=":material/download:",
            type="primary",
            disabled=df.empty,
        )
        st.caption("Exports the records currently shown above.")

    with d2:
        if not df.empty:
            with st.expander("Delete a record"):
                options = {
                    f"{r['ID']}: {r['Child name']} ({r['Parent name']})": int(r["ID"])
                    for _, r in df.iterrows()
                }
                choice = st.selectbox("Select record", list(options.keys()), index=None)
                if st.button("Delete record", icon=":material/delete:", disabled=choice is None):
                    with engine.begin() as conn:
                        conn.execute(children.delete().where(children.c.id == options[choice]))
                    st.rerun()

# ---------------------------------------------------------------------------
# Tab 3: Form fields (add extra fields)
# ---------------------------------------------------------------------------
with tab_fields:
    st.markdown("Add extra fields to the form, for example **Gender**, **Admission number** or **Phone number**.")

    with st.form("field_form", clear_on_submit=True):
        n1, n2 = st.columns(2)
        new_name = n1.text_input("Field name")
        new_type = n2.selectbox("Field type", FIELD_TYPES)
        new_options = st.text_input(
            "Dropdown options",
            placeholder="Separate with commas, e.g. Male, Female",
            help="Only used when the field type is Dropdown.",
        )
        new_required = st.checkbox("Required")
        add_field = st.form_submit_button("Add field", icon=":material/add:", type="primary")

    if add_field:
        name = new_name.strip()
        existing = {f["name"].lower() for f in fields} | {
            "parent name", "child name", "age", "grade", "school", "id", "date added"
        }
        if not name:
            st.error("Field name is required.", icon=":material/error:")
        elif name.lower() in existing:
            st.error("A field with that name already exists.", icon=":material/error:")
        elif new_type == "Dropdown" and not new_options.strip():
            st.error("Please add options for the dropdown.", icon=":material/error:")
        else:
            with engine.begin() as conn:
                conn.execute(
                    custom_fields.insert().values(
                        name=name,
                        field_type=new_type,
                        options=new_options.strip() if new_type == "Dropdown" else None,
                        required=1 if new_required else 0,
                    )
                )
            st.rerun()

    st.markdown("**Current extra fields**")
    if not fields:
        st.caption("No extra fields yet.")
    else:
        for f in fields:
            r1, r2 = st.columns([5, 1])
            detail = f["field_type"] + (", required" if f["required"] else "")
            if f["field_type"] == "Dropdown" and f["options"]:
                detail += f" ({f['options']})"
            r1.markdown(f"**{f['name']}**  \n{detail}")
            if r2.button("Remove", key=f"rm_{f['id']}", icon=":material/delete:"):
                with engine.begin() as conn:
                    conn.execute(custom_fields.delete().where(custom_fields.c.id == f["id"]))
                st.rerun()
        st.caption("Removing a field hides it from the form. Data already saved for it stays in the database and in Excel exports.")
