import hmac
import json
import os
import re
import time
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
    inspect,
    select,
    text,
)

st.set_page_config(
    page_title="Brian Kathurima | Children Data Collection",
    page_icon=":material/child_care:",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Settings (secrets)
# ---------------------------------------------------------------------------
# Add these to .streamlit/secrets.toml (or the Secrets box on Streamlit Cloud):
#   DATABASE_URL = "postgresql://user:password@host:5432/postgres"
#   APP_USERNAME = "choose-a-username"
#   APP_PASSWORD = "choose-a-strong-password"


def get_secret(name: str, default=None):
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.getenv(name, default)


def get_db_url() -> str:
    url = get_secret("DATABASE_URL", "sqlite:///children.db")
    # Always use the psycopg (v3) driver for Postgres, whatever prefix was pasted
    for prefix in ("postgresql+psycopg2://", "postgresql://", "postgres://"):
        if url.startswith(prefix):
            url = "postgresql+psycopg://" + url[len(prefix):]
            break
    return url


# ---------------------------------------------------------------------------
# Heading and styling
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    .block-container { padding-top: 1.5rem; max-width: 1100px; }
    .banner {
        background: #0f5132;
        color: #ffffff;
        border-radius: 14px;
        padding: 1.6rem 1.8rem;
        margin-bottom: 1.25rem;
        text-align: center;
    }
    .banner .name {
        font-size: clamp(2rem, 6vw, 3.4rem);
        font-weight: 800;
        line-height: 1.05;
        letter-spacing: 0.02em;
        text-transform: uppercase;
        margin: 0;
    }
    .banner .role {
        font-size: clamp(1rem, 3vw, 1.5rem);
        font-weight: 700;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        margin-top: 0.55rem;
        color: #d1e7dd;
    }
    .banner .sub {
        display: inline-flex; align-items: center; gap: 8px;
        margin-top: 0.9rem; font-size: 0.95rem; opacity: 0.9;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Lucide "users" icon, inline so it follows the banner colour
LUCIDE_USERS = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>'
    '<circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/>'
    '<path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>'
)

st.markdown(
    f"""
    <div class="banner">
        <div class="name">Brian Kathurima</div>
        <div class="role">MCA Aspirant | Abo Central Ward 2027</div>
        <div class="sub">{LUCIDE_USERS}<span>Children Data Collection</span></div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


def login_page():
    expected_user = get_secret("APP_USERNAME")
    expected_pass = get_secret("APP_PASSWORD")

    if not expected_user or not expected_pass:
        st.error(
            "Login is not set up yet. Add APP_USERNAME and APP_PASSWORD to the app secrets.",
            icon=":material/lock:",
        )
        return

    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        with st.form("login_form"):
            st.markdown("#### Sign in")
            username = st.text_input("Username", icon=":material/person:")
            password = st.text_input("Password", type="password", icon=":material/key:")
            go = st.form_submit_button("Sign in", icon=":material/login:", type="primary", use_container_width=True)

        if go:
            ok_user = hmac.compare_digest(username.strip().encode(), str(expected_user).encode())
            ok_pass = hmac.compare_digest(password.encode(), str(expected_pass).encode())
            if ok_user and ok_pass:
                st.session_state["auth"] = True
                st.rerun()
            else:
                time.sleep(1.5)  # slows down guessing
                st.error("Incorrect username or password.", icon=":material/error:")


if not st.session_state.get("auth"):
    login_page()
    st.stop()

# Signed in: small sign out button
_, out_col = st.columns([6, 1])
with out_col:
    if st.button("Sign out", icon=":material/logout:", use_container_width=True):
        st.session_state["auth"] = False
        st.rerun()

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
metadata = MetaData()

children = Table(
    "children",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("parent_name", String(150), nullable=False),
    Column("parent_contact", String(50), nullable=True),
    Column("child_name", String(150), nullable=False),
    Column("gender", String(20), nullable=True),
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


def ensure_columns(engine):
    """Adds the gender and parent_contact columns if the table already exists without them."""
    existing = {c["name"] for c in inspect(engine).get_columns("children")}
    wanted = {"parent_contact": "VARCHAR(50)", "gender": "VARCHAR(20)"}
    with engine.begin() as conn:
        for name, ddl in wanted.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE children ADD COLUMN {name} {ddl}"))


@st.cache_resource
def get_engine():
    engine = create_engine(get_db_url(), pool_pre_ping=True)
    metadata.create_all(engine)
    ensure_columns(engine)
    return engine


engine = get_engine()

GRADES = (
    ["PP1", "PP2"]
    + [f"Grade {i}" for i in range(1, 13)]
    + ["Other"]
)

GENDERS = ["Male", "Female"]
FIELD_TYPES = ["Text", "Number", "Date", "Dropdown"]
BUILT_IN_NAMES = {
    "id", "parent name", "parent contact", "child name",
    "gender", "age", "grade", "school", "date added",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def clean_phone(raw: str):
    """Returns a phone number as 07XXXXXXXX or 01XXXXXXXX, or None if it is not valid."""
    p = re.sub(r"[\s\-()]", "", raw or "")
    m = re.fullmatch(r"(?:\+?254|0)([71]\d{8})", p)
    return "0" + m.group(1) if m else None


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
            "Parent contact": r["parent_contact"],
            "Child name": r["child_name"],
            "Gender": r["gender"],
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

    base_cols = [
        "ID", "Parent name", "Parent contact", "Child name", "Gender",
        "Age", "Grade", "School", "Date added",
    ]
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
        parent_contact = c2.text_input("Parent contact", placeholder="e.g. 0712345678")

        c3, c4 = st.columns(2)
        child_name = c3.text_input("Child name", placeholder="e.g. Brian Mwangi")
        gender = c4.selectbox("Gender", GENDERS, index=None, placeholder="Select gender")

        c5, c6 = st.columns(2)
        age = c5.number_input("Age", min_value=0, max_value=25, value=None, step=1, placeholder="Enter age")
        grade = c6.selectbox("Grade", GRADES, index=None, placeholder="Select grade")

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
        phone = clean_phone(parent_contact)
        if not parent_name.strip():
            errors.append("Parent name is required.")
        if not parent_contact.strip():
            errors.append("Parent contact is required.")
        elif phone is None:
            errors.append("Enter a valid phone number, for example 0712345678.")
        if not child_name.strip():
            errors.append("Child name is required.")
        if gender is None:
            errors.append("Gender is required.")
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
                        parent_contact=phone,
                        child_name=child_name.strip(),
                        gender=gender,
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
    search = f1.text_input("Search", placeholder="Search by parent, child, contact or school", icon=":material/search:")
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
    st.markdown("Add extra fields to the form, for example **Admission number** or **Home village**.")

    with st.form("field_form", clear_on_submit=True):
        n1, n2 = st.columns(2)
        new_name = n1.text_input("Field name")
        new_type = n2.selectbox("Field type", FIELD_TYPES)
        new_options = st.text_input(
            "Dropdown options",
            placeholder="Separate with commas, e.g. Day, Boarding",
            help="Only used when the field type is Dropdown.",
        )
        new_required = st.checkbox("Required")
        add_field = st.form_submit_button("Add field", icon=":material/add:", type="primary")

    if add_field:
        name = new_name.strip()
        existing = {f["name"].lower() for f in fields} | BUILT_IN_NAMES
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
