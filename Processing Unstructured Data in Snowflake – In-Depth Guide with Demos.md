# Processing Unstructured Data in Snowflake

**Snowflake Cortex AI \+ Openflow \+ Snowpark for documents, media, and free text (with demos)**

---

## 1\. Conceptual Overview

Snowflake now treats **unstructured data** (documents, images, audio, video, arbitrary binaries) as a first‑class citizen alongside structured and semi‑structured data. Unstructured data is stored in **stages**, modeled via the **FILE** data type, and processed with:

- **Cortex AI Functions (AISQL)** – SQL and Python functions for text, documents, images, audio (e.g., `AI_EXTRACT`, `AI_PARSE_DOCUMENT`, `AI_TRANSCRIBE`, `AI_SENTIMENT`, `AI_EMBED`).  
- **Cortex Search** – fully managed **hybrid (vector \+ keyword \+ rerank)** search on text data, designed as the RAG engine for chatbots and enterprise search over unstructured content.  
- **Document AI → AI\_EXTRACT** – LLM‑powered document understanding, moving from the older DocAI UI to the API‑first `AI_EXTRACT` pattern for scalable extraction.  
- **Snowpark & external access** – Python/Java/Scala UDFs/UDTFs and external functions for custom OCR, CV, or external model calls.  
- **Openflow / Unstructured connectors** – managed ingestion from SharePoint, Google Drive, Box, Slack, Confluence, etc., into stages \+ Cortex Search indexes with ACL preservation.

At the platform level, Snowflake integrates **structured, semi‑structured, and unstructured** data in one governed environment, with directory tables, replication, and secure URLs for safe file access.

---

## 2\. Storage Model: FILE Type, Stages, Directory Tables

### 2.1 Unstructured data types and FILE

Snowflake distinguishes:

- **Structured** – classic tables (CSV, relational, etc.)  
- **Semi‑structured** – JSON, XML, etc., in `VARIANT` columns  
- **Unstructured** – documents, images, audio, etc., stored as **files on stages** and referenced via the **`FILE` data type**.

A `FILE` value is just **metadata \+ locator**, not the actual bytes, and includes fields like `STAGE`, `RELATIVE_PATH`, `CONTENT_TYPE`, `SIZE`, `ETAG`, `LAST_MODIFIED`, plus stage/file URLs.

Key constructors & accessors:

- `TO_FILE`, `TRY_TO_FILE` – construct `FILE` values from stage/path or URLs.  
- `FL_GET_*` functions – inspect file metadata (content type, size, URLs, etc.).

### 2.2 Stages and directory tables

Unstructured data lives on:

- **Internal stages** (Snowflake‑managed storage)  
- **External stages** (S3, Azure Blob, GCS, and **S3‑compatible** storage like Cloudflare R2, Pure, Dell, etc.)

Stages with `DIRECTORY = TRUE` automatically maintain a **directory table**:

```sql
CREATE STAGE my_docs
  DIRECTORY = TRUE;

SELECT * FROM DIRECTORY(@my_docs);
```

Directory table columns include file path, size, MD5, last modified, and URLs for each file.

### 2.3 Secure file access (presigned, file, and scoped URLs)

Common URL patterns:

- **Presigned URL** – short‑lived, client‑consumable link for downloading a file.  
- **Stage file URL** – signed URL referencing a staged file.  
- **Scoped file URL** – URL generated in a **view using owner’s rights**, scoped to the querying user/role and expiring automatically.

**Demo 1 – Basic unstructured data storage \+ secure access**

```sql
-- 1) Create an internal stage for documents
CREATE OR REPLACE STAGE documents_stage
  DIRECTORY = TRUE;

-- 2) (Client side) Upload PDFs to the stage
--   Example with SnowSQL:
--   !PUT file:///local/path/contracts/*.pdf @documents_stage AUTO_COMPRESS=FALSE;

-- 3) Inspect the directory table
SELECT FILE_PATH, SIZE, LAST_MODIFIED
FROM DIRECTORY(@documents_stage);

-- 4) Create a FILE value for a specific document
SELECT TO_FILE('@documents_stage', 'contracts/contract_001.pdf') AS contract_file;

-- 5) Generate a one‑off presigned URL for download
SELECT GET_PRESIGNED_URL(@documents_stage, 'contracts/contract_001.pdf') AS download_url;

-- 6) Use a scoped URL in a secure view for filtered sharing
CREATE OR REPLACE VIEW v_abc_bank_contracts AS
SELECT
  *,
  BUILD_SCOPED_FILE_URL(@documents_stage, RELATIVE_FILE_PATH) AS scoped_url
FROM DIRECTORY(@documents_stage)
WHERE FILE_PATH LIKE 'contracts/%'
  AND FILE_PATH ILIKE '%ABC_BANK%';
```

This pattern lets you **share only the subset** of files a consumer should see, without exposing the raw stage or storage credentials.

---

## 3\. Ingestion Patterns for Unstructured Data

### 3.1 Direct upload and COPY FILES

For single/batch moves you can:

- Upload from a client using `PUT` (SnowSQL) or UI.  
- Use `COPY FILES` to copy between stages and external locations:

```sql
-- Import files from external S3 bucket into an internal stage
COPY FILES
  FROM @ext_raw_docs
  TO   @documents_stage
  PATTERN='.*\.(pdf|docx)$';
```

`COPY FILES` works across **cloud object storage and S3‑compatible endpoints**, with one command, and participates in RBAC & replication like other Snowflake objects.

### 3.2 Openflow unstructured connectors

For large enterprises with content spread across SaaS systems, **Openflow connectors** (SharePoint, Google Drive, Box, Slack, Confluence, etc.):

- Continuously ingest documents \+ **ACLs** into stages and tables.  
- Normalize raw content (bronze) → parsed/chunked (silver) → embedded (gold).  
- Feed **Cortex Search services** and **Snowflake Intelligence / Cortex Agents** with unified unstructured corpora.

Figure 1 shows an example architecture:

[Image: Openflow unstructured ingestion to Cortex Search](https://snowflake-be.glean.com/api/v1/images?key=eyJ0eXBlIjoiRE9DVU1FTlRfSU1BR0UiLCJpZCI6ImZlZGRjMTgwMWIyYzJkNGY0M2QyZjc0YzIzM2JlZGYyOWE3ZTcyNmQ2OTgzMjUwMzhjYjc5ODkwMzA2NzYxNWQiLCJkb2NpZCI6IkdEUklWRV8xTHlBWmpOMDU5RERHR3E5dlVWYmtTbDNCNzRkZk1yUE5yRXZHS0JHaHRWUSIsImV4dCI6Ii5wbmcifQ==)

*Figure 1: Openflow ingests documents \+ ACLs from SharePoint/Drive/Slack/Box/Confluence, parses & chunks them, embeds via Cortex, and serves them through Cortex Search, Snowflake Intelligence, and custom AI apps.*

This is the **recommended pattern** for “talk to my SharePoint/GDrive/Slack content” use cases.

---

## 4\. SQL‑First Processing with Cortex AI Functions (AISQL)

Cortex AI Functions let you **process unstructured content in pure SQL** (and in Python APIs) using Snowflake‑hosted LLMs, including Snowflake Arctic, Mistral, Reka, Anthropic, etc.

Key functions for unstructured data include:

- `AI_PARSE_DOCUMENT` – layout‑aware parsing of PDFs and similar docs into structured text.  
- `AI_EXTRACT` – schema‑driven extraction of fields from documents.  
- `AI_COMPLETE` – text and multimodal completion (including image \+ text).  
- `AI_TRANSCRIBE` – speech‑to‑text for audio/video.  
- `AI_SENTIMENT`, `AI_CLASSIFY`, `AI_FILTER` – sentiment, classification, and natural‑language filters on text.  
- `AI_EMBED`, `AI_SIMILARITY` – generate embeddings and run similarity search.

### 4.1 Demo 2 – Turn a PDF table into a structured table with AI\_EXTRACT

Suppose invoices or SEC filings contain a **tabular** section you want to analyze in SQL.

```sql
-- 1) Ensure files are staged
-- e.g., @documents_stage/Table_Extraction_Test.pdf

-- 2) Use AI_EXTRACT with a JSON schema for the desired output
WITH extracted AS (
  SELECT
    AI_EXTRACT(
      file => TO_FILE('@documents_stage', 'Table_Extraction_Test.pdf'),
      response_format => OBJECT_CONSTRUCT(
        'schema', OBJECT_CONSTRUCT(
          'type', 'object',
          'properties', OBJECT_CONSTRUCT(
            'items', OBJECT_CONSTRUCT(
              'description', 'Local Currency ARPU by country and quarter (row‑major).',
              'type', 'object',
              'properties', OBJECT_CONSTRUCT(
                'country', OBJECT_CONSTRUCT('type', 'array'),
                'quarter', OBJECT_CONSTRUCT('type', 'array'),
                'arpu_value', OBJECT_CONSTRUCT('type', 'array')
              )
            )
          )
        )
      )
    ) AS resp
)
SELECT
  value:country::STRING  AS country,
  value:quarter::STRING  AS quarter,
  value:arpu_value::FLOAT AS arpu_value
FROM extracted,
LATERAL FLATTEN(input => resp:"response":"items");
```

This pattern is what Snowflake’s own “Document Tables to Structured Data” examples use for ARPU tables and similar layouts.

### 4.2 Demo 3 – Entity extraction from contracts or 10‑K PDFs

```sql
-- Example: extract company name, CEO, and business description
SELECT
  AI_EXTRACT(
    file => TO_FILE('@documents_stage', '10K_SNOWFLAKE_2024.pdf'),
    response_format => OBJECT_CONSTRUCT(
      'CEO',                 'Who is the CEO?',
      'Company_name',        'What is the company name?',
      'Business_Description','What are the company\'s main products, services, and operations?'
    )
  ) AS resp;
```

Typical output:

```json
{
  "response": {
    "Company_name": "Snowflake Inc.",
    "CEO": "Sridhar Ramaswamy",
    "Business_Description": "Our platform is the innovative technology that powers the Data Cloud..."
  }
}
```

You can **extract directly into relational tables** for downstream analytics or RAG filters.

### 4.3 Demo 4 – Transcript summarization and sentiment

Assume you have call transcripts in a `CALL_TRANSCRIPTS` table with a `TRANSCRIPT_TEXT` column.

```sql
-- Summarize each transcript
CREATE OR REPLACE TABLE CALL_SUMMARIES AS
SELECT
  CALL_ID,
  AI_AGG(
    'Summarize the key points of this customer support interaction.',
    TRANSCRIPT_TEXT
  ) AS SUMMARY
FROM CALL_TRANSCRIPTS
GROUP BY CALL_ID;

-- Aspect‑based sentiment (e.g., product vs. agent)
CREATE OR REPLACE TABLE CALL_SENTIMENT AS
SELECT
  CALL_ID,
  AI_EXTRACT(
    text => TRANSCRIPT_TEXT,
    response_format => OBJECT_CONSTRUCT(
      'product_sentiment', 'What is the customer sentiment about the product? Answer with a number between -1 and 1.',
      'agent_sentiment',   'What is the sentiment about the support agent? Answer with a number between -1 and 1.'
    )
  ) AS SENTIMENT_JSON
FROM CALL_TRANSCRIPTS;
```

This matches the common “call center optimization” patterns used in FSI decks: summarization, profile building, and sentiment over call transcripts \+ metadata.

---

## 5\. Document AI → AI\_EXTRACT Migration Pattern

The legacy **Document AI UI** (DocAI app) is being deprecated in favor of **API‑first pipelines using `AI_EXTRACT`** powered by the Arctic‑based extraction model (`arctic-extract`).

Key migration points:

- DocAI’s `model_name!PREDICT` calls are replaced by `AI_EXTRACT` with a JSON schema describing what to extract (no manual labeling UI required).  
- `AI_EXTRACT` runs zero‑copy inference against files in **internal or external stages**, avoiding data duplication.  
- Fine‑tuning for domain‑specific layouts becomes part of the **Cortex fine‑tuning** surface, not the DocAI UI.

**Demo 5 – Replacing a DocAI model with AI\_EXTRACT**

If you previously had:

```sql
-- Legacy style (conceptual)
SELECT my_docai_model!PREDICT(
  TO_FILE('@documents_stage', 'claim_123.pdf')
) AS prediction;
```

You refactor to:

```sql
-- New pattern with AI_EXTRACT
SELECT
  AI_EXTRACT(
    file => TO_FILE('@documents_stage', 'claim_123.pdf'),
    response_format => OBJECT_CONSTRUCT(
      'policy_number',      'What is the policy number?',
      'claim_amount',       'What is the claim amount in dollars?',
      'incident_date',      'On what date did the incident occur?',
      'fraud_risk_flag',    'Is there any indication of fraud risk? Answer true or false.'
    )
  ) AS claim_info;
```

Then persist `claim_info:response` into a claims table for downstream analytics and RAG filters (e.g., as attributes in Cortex Search).

---

## 6\. Cortex Search: Retrieval over Unstructured Text

**Cortex Search** is Snowflake’s **fully managed hybrid search engine** for text data (semantic vector \+ keyword \+ reranking), designed for:

- **RAG chatbots** (“chat with your PDFs / contracts / tickets”)  
- **Enterprise search** over docs, logs, tickets, CRM notes, etc.

It abstracts embeddings, indexes, refresh, and serving: you declare **what to index** and search with a JSON query API.

### 6.1 Demo 6 – Build a Cortex Search Service on support transcripts

**Step 1 – Create sample table \+ enable change tracking**

```sql
CREATE OR REPLACE TABLE SUPPORT_TRANSCRIPTS (
  TRANSCRIPT_TEXT STRING,
  REGION          STRING,
  AGENT_ID        STRING
);

ALTER TABLE SUPPORT_TRANSCRIPTS SET CHANGE_TRACKING = TRUE;
```

**Step 2 – Create Cortex Search service**

```sql
CREATE OR REPLACE CORTEX SEARCH SERVICE transcript_search_svc
  ON TRANSCRIPT_TEXT
  ATTRIBUTES REGION, AGENT_ID
  WAREHOUSE = cortex_search_wh
  TARGET_LAG = '1 day'
  EMBEDDING_MODEL = 'snowflake-arctic-embed-l-v2.0'
AS
  SELECT
    TRANSCRIPT_TEXT,
    REGION,
    AGENT_ID
  FROM SUPPORT_TRANSCRIPTS;
```

This defines:

- **Search column**: `TRANSCRIPT_TEXT`  
- **Attributes** (metadata filters): `REGION`, `AGENT_ID`  
- **Index freshness**: refresh within `TARGET_LAG` using the specified warehouse  
- **Embedding model**: high‑quality multilingual Arctic embed model.

**Step 3 – Preview results via SQL**

```sql
SELECT PARSE_JSON(
  SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
    'cortex_search_db.services.transcript_search_svc',
    '{
       "query":  "internet issues in 2023",
       "columns": ["TRANSCRIPT_TEXT", "REGION", "AGENT_ID"],
       "filter":  {"@eq": {"REGION": "North America"}},
       "limit":   5
     }'
  )
)['results'] AS results;
```

This uses the same hybrid retrieval logic Snowflake exposes in the docs and best‑practices guides.

**Step 4 – Query via Python (Snowpark \+ Core)**

```py
from snowflake.snowpark import Session
from snowflake.core import Root

session = Session.builder.configs(CONNECTION_PARAMETERS).create()
root = Root(session)

svc = (
    root.databases["CORTEX_SEARCH_DB"]
        .schemas["SERVICES"]
        .cortex_search_services["TRANSCRIPT_SEARCH_SVC"]
)

resp = svc.search(
    query="internet issues in 2023",
    columns=["TRANSCRIPT_TEXT", "REGION", "AGENT_ID"],
    filter={"@eq": {"REGION": "North America"}},
    limit=3,
)

print(resp.to_json())
```

This is ideal for **apps, agents, and MCP tools** that need low‑latency retrieval without warehouses.

### 6.2 Best practices highlights

From internal best‑practice guides and docs:

- **Chunk text** to \~512 tokens using `SPLIT_TEXT_RECURSIVE_CHARACTER` for better vector retrieval.  
- Choose **embedding model** based on language/length/cost:  
  - `snowflake-arctic-embed-m-v1.5` – fast, low‑cost English.  
  - `snowflake-arctic-embed-l-v2.0` – multilingual, higher‑quality general purpose.  
  - `snowflake-arctic-embed-l-v2.0-8k` – long context docs.  
- Use **attributes** for relational filters (e.g., region, customer\_id, year).  
- For existing vector stores, consider **BYO Embeddings** with `VECTOR INDEX` to avoid re‑embedding when migrating.

---

## 7\. Agents & Snowflake Intelligence: Orchestrating Structured \+ Unstructured

**Cortex Agents** orchestrate across:

- **Cortex Analyst** – NL → SQL on semantic views (structured).  
- **Cortex Search** – semantic \+ keyword search on unstructured text.  
- **Custom tools** – UDFs, stored procedures, external APIs, MCP tools.

Snowflake Intelligence is the **UI product** that sits on top of Agents to let business users “talk to their data” (structured \+ unstructured) via conversational search and analysis.

### 7.1 Demo 7 – Wiring a Cortex Search service into an Agent

After creating a Cortex Search service (`transcript_search_svc`), you expose it as an **agent tool**:

```
tools:
  - tool_spec:
      type: "cortex_search"
      name: "support_transcript_search"
      description: "Search customer support transcripts by topic and region"
    tool_resources:
      support_transcript_search:
        name: "CORTEX_SEARCH_DB.SERVICES.TRANSCRIPT_SEARCH_SVC"
        max_results: "5"
        filter:
          "@eq":
            REGION: "North America"
        title_column: "AGENT_ID"
        id_column:    "AGENT_ID"
```

The agent can now:

- Use Analyst for “Top issues by region last 30 days” (structured).  
- Use Cortex Search for “Find transcripts where customers complained about sound quality at Jazz Night” (unstructured).

Snowflake Intelligence uses the same Agents API under the hood, so your **Cortex Search services are reusable** across custom apps, Slack/Teams bots, and SI itself.

---

## 8\. Custom Processing with Snowpark & External Access

When AISQL or Doc functions aren’t enough, you can drop to **Snowpark** or **external functions**.

### 8.1 Demo 8 – Python UDF reading a staged PDF with SnowflakeFile

This is the canonical pattern from the Unstructured docs:

```sql
-- 1) Python UDF to read a staged PDF and return extracted text
CREATE OR REPLACE FUNCTION pdf_to_text(file_url STRING)
RETURNS STRING
LANGUAGE PYTHON
RUNTIME_VERSION = '3.9'
PACKAGES = ('snowflake-snowpark-python', 'pypdf2')
HANDLER = 'pdfparser'
AS
$$
from snowflake.snowpark.files import SnowflakeFile
from PyPDF2 import PdfReader
from io import BytesIO

def pdfparser(file_url: str) -> str:
    # file_url should be a scoped or stage file URL
    with SnowflakeFile.open(file_url, 'rb') as f:
        data = f.read()
    reader = PdfReader(BytesIO(data))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages)
$$;

-- 2) Call UDF with a scoped file URL
SELECT
  pdf_to_text(
    BUILD_SCOPED_FILE_URL(@documents_stage, 'contracts/contract_001.pdf')
  ) AS contract_text;
```

This pattern supports **arbitrary libraries** (PyPDF2, PIL, Tesseract wrappers, custom tokenizers, etc.) while keeping data inside Snowflake’s security perimeter.

### 8.2 Demo 9 – External function to call a custom OCR/LLM API

If you already have an external doc processing API, you can wrap it:

```sql
CREATE OR REPLACE EXTERNAL FUNCTION extract_document_data(presigned_url STRING)
RETURNS VARIANT
API_INTEGRATION = document_apis
AS 'https://your-api-gateway.example.com/prod/extract_document_data';

-- Use with a presigned URL to the staged file
SELECT extract_document_data(
  GET_PRESIGNED_URL(@documents_stage, 'scanned_form_001.pdf')
) AS doc_json;
```

With **External Network Access**, the same approach works from Snowpark UDFs without an API Gateway, using network rules to restrict outbound hosts.

---

## 9\. Governance, Security, and Observability

### 9.1 Roles and privileges

Key database roles:

- `SNOWFLAKE.CORTEX_USER` – call LLM/AISQL functions (`AI_COMPLETE`, `AI_EXTRACT`, etc.).  
- `SNOWFLAKE.CORTEX_EMBED_USER` – create Cortex Search services that do their own embeddings (`AI_EMBED`, `EMBED_TEXT_768/1024`).

Cortex and Openflow features adhere to **Snowflake RBAC**, masking policies, and row access policies:

- AI functions see only data your role is allowed to see.  
- Unstructured connectors can preserve **ACLs from source systems**, which are then respected in query and search layers.

### 9.2 Cost and usage visibility

For **Cortex Search**, cost comes from:

- **Indexing compute** (warehouse to build and refresh index according to `TARGET_LAG`).  
- **Embedding tokens** (per token embedded with the chosen embedding model).  
- **Serving compute** (GB/month of indexed data stored and served by the multi‑tenant serving tier).

Views like:

- `CORTEX_SEARCH_DAILY_USAGE_HISTORY`  
- `CORTEX_SEARCH_SERVING_USAGE_HISTORY`

help track index size, serving costs, and refresh behavior.

For AISQL, usage is visible via `COMPLETION_USAGE_HISTORY` and related account usage views.

---

## 10\. End‑to‑End Patterns by Use Case

### 10.1 PDF / contract analytics and RAG

1. **Ingest**: Store PDFs in internal/external stages (direct PUT or Openflow).  
2. **Parse & extract**: Use `AI_EXTRACT`/`AI_PARSE_DOCUMENT` \+ optional Snowpark to produce a **contracts table** with normalized fields (parties, dates, amounts, key clauses).  
3. **Index for search**: Build a Cortex Search service over both raw text and key fields as attributes.  
4. **Expose via Agents**: Use Agents with Cortex Search \+ Analyst for “Compare contract terms between vendors A and B” or “Show contracts expiring next 90 days with change‑of‑control clauses.”

### 10.2 Call center analytics on transcripts \+ tickets

1. **Ingest**: Store audio → `AI_TRANSCRIBE` → transcripts table; or ingest transcripts directly.  
2. **Enrich**: Use `AI_AGG` and `AI_SENTIMENT` for summary and sentiment features; join with CRM/CSAT tables.  
3. **Search & RAG**: Build a Cortex Search service on transcripts and use Agents/SI to answer NL questions about issues, root causes, and churn risk.  
4. **Downstream ML**: Use Snowflake ML/Feature Store for churn/propensity models using both structured and derived unstructured features.

### 10.3 Enterprise search across SharePoint/Drive/Slack

1. **Ingest**: Configure Openflow unstructured connectors (SharePoint, GDrive, Slack, Box, Confluence) → stages \+ normalized doc table \+ ACLs.  
2. **Index**: Create one or more Cortex Search services per corpus/domain (e.g., “Policies & Procedures”, “Engineering Docs”).  
3. **Access**:  
   - Directly via Python/REST for custom apps.  
   - As Cortex Search tools in Agents powering Snowflake Intelligence, Slack bots, or custom UIs.  
4. **Governance**: Let source ACLs \+ Snowflake RBAC jointly determine visibility for search results and citations.

---

## 11\. Summary

Snowflake’s current stack for unstructured data combines:

- **Robust storage & access** – FILE type, stages, directory tables, replication, secure URLs.  
- **AISQL & Document intelligence** – `AI_EXTRACT`, `AI_PARSE_DOCUMENT`, `AI_COMPLETE`, `AI_TRANSCRIBE`, etc., to turn raw documents, audio, and images into analytics‑ready assets.  
- **Cortex Search** – hybrid search with state‑of‑the‑art retrieval quality for RAG and enterprise search.  
- **Agents & Snowflake Intelligence** – orchestrating structured \+ unstructured sources to deliver grounded answers.  
- **Snowpark & Openflow** – custom ML logic and large‑scale, governed ingestion from content systems.

The demos above give you **runnable templates** you can adapt directly into customer‑facing PoCs and internal accelerators for FSI and beyond, from call center analytics to contract intelligence and enterprise search on unstructured data.

---

## Sources

- [Snowflake Cortex AI Functions (including LLM functions) | Snowflake Documentation](https://docs.snowflake.com/en/user-guide/snowflake-cortex/aisql)  
- [2026 Unstructured Data Processing](https://docs.google.com/presentation/d/1tB_43u88fdXADxmi4wVWevEPHRszgwzkGoy8PH1jrG0)  
- [Cortex Search | Snowflake Documentation](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-search/cortex-search-overview)  
- [Cortex Search | Comprehensive Guide](https://snowflakecomputing.atlassian.net/wiki/spaces/SKE/pages/4521852948)  
- [Unstructured Data Processing](https://docs.google.com/presentation/d/1d7dg9ZQSpVhuc9IoTX_uy-CBZ8ZaCoiwdWWdiC6y4iw)  
- [Unstructured Data \- Overview & Deep Dive \- Deck](https://docs.google.com/presentation/d/19YbThFdD2sBTSOEVLX-gFMH4QpWNT3vfoViqm8pLexk)  
- [Openflow Unstructured Data & Streaming Connectors \- Feature Friday October 2025](https://docs.google.com/presentation/d/1LyAZjN059DDGGq9vUVbkSl3B74dfMrPNrEvGKBGhtVQ)  
- [Snowflake Connectors | Snowflake Documentation](https://other-docs.snowflake.com/en/connectors)  
- [Unstructured data types | Snowflake Documentation](https://docs.snowflake.com/en/sql-reference/data-types-unstructured)  
- [FSI Cortex AI Overview \- Jan 2026.pdf](https://drive.google.com/file/d/1viseBk65x5jMZrk3kOf6y_TRtBaj6ZEy)  
- [CORTEX\_DOCUMENT\_PROCESSING\_USAGE\_HISTORY view | Snowflake Documentation](https://docs.snowflake.com/en/sql-reference/account-usage/cortex_document_processing_usage_history)  
- [Cortex Search \- Aug 2024](https://docs.google.com/presentation/d/1m8yftx7fg7dFWg3UtkjlHfTRUq5Suxhz1mYzMXiLwWI)  
- [Cortex Search | Comprehensive Guide](https://snowflakecomputing.atlassian.net/wiki/spaces/SKE/pages/4521852948)  
- [Best Practices Guide for Cortex Search on Snowflake](https://snowflakecomputing.atlassian.net/wiki/spaces/SKE/pages/4535156994)  
- [Snowflake Cortex Features: Best Practices Guide](https://snowflakecomputing.atlassian.net/wiki/spaces/SKE/pages/4711481919)  
- [Thread between Nikolai and Euan](https://snowflake.slack.com/archives/C07ENMWNQ3F/p1773406888746829?thread_ts=1773406888.746829&cid=C07ENMWNQ3F)  
- [Overview of Snowflake Intelligence | Snowflake Documentation](https://docs.snowflake.com/en/user-guide/snowflake-cortex/snowflake-intelligence)  
- [LLM Lifecycle](https://snowflakecomputing.atlassian.net/wiki/spaces/SKE/pages/4368892904)  
- [Optional: Slack Integration with Cortex Agent API](https://snow.gitlab-dedicated.com/snowflakecorp/SE/sales-engineering/collegeai/-/blob/main/Q4_FY26_SI_HOL/Optional_Slack_Integration/README.md)  
- [Unstructured Data Processing](https://docs.google.com/presentation/d/1d7dg9ZQSpVhuc9IoTX_uy-CBZ8ZaCoiwdWWdiC6y4iw)  
- [Use Case \- PDF Chatbot with Document AI & Cortex Search](https://snowflakecomputing.atlassian.net/wiki/spaces/SKE/pages/4056023112)  
- [Novo Nordisk | Snowflake Unstructured Data Processing & Management Framework](https://docs.google.com/presentation/d/161H9-PTzWmjvcVwXtqvEC7tcrBFbzKJJTWtX4caprZ8)

*Written with Glean Assistant*  
