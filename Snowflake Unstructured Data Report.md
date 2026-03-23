# **Comprehensive Guide: Processing Unstructured Data in Snowflake**

Unstructured data—PDFs, images, audio, video, and proprietary formats—now accounts for over 80% of enterprise data. Snowflake has evolved from a cloud data warehouse into an **AI Data Cloud**, providing native capabilities to store, govern, and process these files at scale without moving data outside its security perimeter.

This report explores the architectural pillars and provides practical demos for handling unstructured workloads.

## **1\. Architectural Foundations**

Processing unstructured data in Snowflake rests on three core components:

### **A. Stages and Directory Tables**

Unstructured files are stored in **Stages** (Internal or External like S3/Azure Blob/GCS). **Directory Tables** provide a built-in catalog of these files, storing metadata such as file size, last modified date, and a "File URL."

### **B. Access Modes (Scoped vs. Pre-signed)**

Snowflake ensures security through different URL types:

* **Scoped URLs:** Encoded, temporary (24h), and only accessible by the user who generated them. Ideal for UDFs.  
* **Pre-signed URLs:** Simple HTTPS links for browser access, with custom expiration times.  
* **File URLs:** Permanent Snowflake-internal identifiers.

### **C. Processing Engines**

* **Snowpark (Python/Java):** For custom logic using open-source libraries (e.g., PyPDF2, Pillow, librosa).  
* **Cortex AI:** High-level SQL functions for LLM-powered extraction, summarization, and translation.  
* **Document AI (Snowflake Arctic-TILT):** A specialized visual interface for training extraction models on complex documents like forms and invoices.

## **2\. Demo 1: Setting up the Foundation**

Before processing, we must catalog our files. This demo shows how to create a stage with a directory table.

\-- Create a database and schema for our unstructured project  
CREATE DATABASE IF NOT EXISTS unstructured\_db;  
CREATE SCHEMA IF NOT EXISTS raw\_data;

\-- 1\. Create a stage (Internal in this example)  
\-- Note: Enable DIRECTORY for metadata tracking  
CREATE OR REPLACE STAGE my\_pdf\_stage  
  DIRECTORY \= (ENABLE \= TRUE)  
  ENCRYPTION \= (TYPE \= 'SNOWFLAKE\_SSE');

\-- 2\. Manually refresh the directory (if using External Stages with AUTO\_REFRESH \= FALSE)  
ALTER STAGE my\_pdf\_stage REFRESH;

\-- 3\. Query the Directory Table to see metadata  
SELECT \* FROM DIRECTORY(@my\_pdf\_stage);

\-- 4\. Generate a Scoped URL for processing  
SELECT   
    RELATIVE\_PATH,   
    BUILD\_SCOPED\_FILE\_URL(@my\_pdf\_stage, RELATIVE\_PATH) AS scoped\_url  
FROM DIRECTORY(@my\_pdf\_stage);

## **3\. Demo 2: Custom Processing with Snowpark Python**

If you need to extract text from a proprietary format or perform OCR using a specific library, Snowpark Python is the best choice.

### **Step 1: Create a Python UDF to read PDF text**

import snowflake.snowpark.files as sf\_files  
from pypdf import PdfReader  
import io

def extract\_pdf\_text(file\_url: str) \-\> str:  
    \# Use SnowflakeFile to securely open the file from the URL  
    with sf\_files.SnowflakeFile.open(file\_url, 'rb') as f:  
        \# Read the file bytes into memory  
        f\_bytes \= f.read()  
        reader \= PdfReader(io.BytesIO(f\_bytes))  
          
        \# Concatenate text from all pages  
        full\_text \= ""  
        for page in reader.pages:  
            full\_text \+= page.extract\_text() \+ "\\n"  
              
    return full\_text

### **Step 2: Register and Run in SQL**

\-- Register the UDF (Assuming pypdf is available in Snowflake Anaconda channel)  
CREATE OR REPLACE FUNCTION parse\_pdf(file\_url STRING)  
RETURNS STRING  
LANGUAGE PYTHON  
RUNTIME\_VERSION \= '3.10'  
PACKAGES \= ('snowflake-snowpark-python', 'pypdf')  
HANDLER \= 'extract\_pdf\_text'  
AS  
$$  
\# \[Python code from above goes here\]  
$$;

\-- Run extraction on all PDFs in the stage  
SELECT   
    RELATIVE\_PATH,   
    parse\_pdf(BUILD\_SCOPED\_FILE\_URL(@my\_pdf\_stage, RELATIVE\_PATH)) as extracted\_content  
FROM DIRECTORY(@my\_pdf\_stage);

## **4\. Demo 3: AI-Powered Extraction with Snowflake Cortex**

The AI\_EXTRACT function (generally available as of late 2025/2026) allows you to extract fields from documents and images using LLMs without writing Python code or training models.

\-- Extracting data from an invoice PDF directly in SQL  
SELECT   
    RELATIVE\_PATH,  
    SNOWFLAKE.CORTEX.AI\_EXTRACT(  
        BUILD\_SCOPED\_FILE\_URL(@my\_pdf\_stage, RELATIVE\_PATH),  
        {  
            'invoice\_number': 'What is the invoice number?',  
            'total\_amount': 'What is the total amount due?',  
            'vendor\_name': 'Who is the vendor?'  
        }  
    ) AS extracted\_json  
FROM DIRECTORY(@my\_pdf\_stage)  
WHERE RELATIVE\_PATH LIKE '%.pdf';

## **5\. Demo 4: Audio Transcription and Sentiment**

Snowflake Cortex also supports AI\_TRANSCRIBE for audio files (MP3, WAV, etc.).

\-- 1\. Setup a stage for audio recordings  
CREATE STAGE call\_recordings DIRECTORY \= (ENABLE \= TRUE);

\-- 2\. Transcribe and Analyze Sentiment in a single pipeline  
SELECT   
    RELATIVE\_PATH,  
    SNOWFLAKE.CORTEX.AI\_TRANSCRIBE(  
        BUILD\_SCOPED\_FILE\_URL(@call\_recordings, RELATIVE\_PATH)  
    ) AS transcript,  
    SNOWFLAKE.CORTEX.SENTIMENT(transcript) AS sentiment\_score  
FROM DIRECTORY(@call\_recordings);

## **6\. Summary of Capabilities (2025-2026)**

| Feature | Primary Use Case | Language | Status (Approx) |
| :---- | :---- | :---- | :---- |
| **Directory Tables** | File cataloging and metadata | SQL | GA |
| **Snowpark Python UDFs** | Custom parsing/OCR/Transformations | Python | GA |
| **Cortex AI\_EXTRACT** | Zero-shot data extraction from docs | SQL | GA |
| **Cortex AI\_TRANSCRIBE** | Audio to Text | SQL | GA |
| **Document AI** | High-precision extraction for complex forms | UI/SQL | GA |
| **Native FILE Type** | Passing file metadata as a first-class type | SQL | GA |

## **7\. Best Practices**

1. **Use Scoped URLs:** Always prefer BUILD\_SCOPED\_FILE\_URL over Pre-signed URLs for internal processing to minimize security risks.  
2. **Warehouse Sizing:** Unstructured processing is often CPU-intensive. Use **Snowpark-optimized warehouses** for large-scale Python processing (Memory-intensive tasks).  
3. **Parallelism:** Snowflake automatically parallelizes UDF execution across the files in a directory table.  
4. **Partitioning:** Organize stages into logical subfolders (/invoices/2024/01/) to improve query performance on directory tables.