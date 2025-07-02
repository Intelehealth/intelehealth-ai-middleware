"""
Medical Diagnosis and Treatment API

This Flask application provides RESTful API endpoints for medical diagnosis assistance,
treatment recommendations, and SNOMED CT terminology management. The application integrates
with AI models for differential diagnosis and treatment planning, and maintains a database
of medical concepts and their mappings.

Key Features:
- Differential diagnosis generation using AI models
- Treatment recommendations based on case history and diagnosis
- SNOMED CT terminology search and management
- Elasticsearch logging for request tracking
- MySQL database integration for concept management

Environment Variables:
- All configuration is loaded from uiux.env file
- Database credentials, API endpoints, and model configurations
- Elasticsearch connection settings
- Retry strategies and timeouts

Author: Medical AI Team
Version: 1.0
"""

import flask
import requests
from requests.adapters import HTTPAdapter

from flask import Flask, request, jsonify, make_response
import base64
import os
import json
import uuid
import sys
import mysql.connector
import pytz
from urllib.request import urlopen
from datetime import datetime as mydt
import urllib.parse
from urllib3.util.retry import Retry
from loggerddx import loggerddx
from loggerttx import loggerttx
from elasticsearch import Elasticsearch
from dotenv import load_dotenv

# Load environment variables from ai.env file
load_dotenv('ai.env')

# Configure retry strategy for HTTP requests
retry_strategy = Retry(
    total=int(os.environ.get('RETRY_TOTAL', 3)),
    backoff_factor=int(os.environ.get('RETRY_BACKOFF_FACTOR', 4)),
    status_forcelist=[int(x) for x in os.environ.get('RETRY_STATUS_FORCELIST', '500,502,503,504').split(',')],
    allowed_methods=["POST"]
)

# Create a session with retry strategy for external API calls
session = requests.Session()
session.mount("http://", HTTPAdapter(max_retries=retry_strategy))
session.mount("https://", HTTPAdapter(max_retries=retry_strategy))

# Initialize Flask application
app = flask.Flask(__name__)
app.config["DEBUG"] = os.environ.get('FLASK_DEBUG', 'False') == 'True'





@app.route('/ddx', methods=["POST"])
def ddx():
    """
    Generate differential diagnosis using AI model.
    
    This endpoint processes patient case history and returns a list of possible
    diagnoses with their likelihood scores and clinical rationale.
    
    Request Body:
        JSON object containing:
        - visitUuid (str): Unique identifier for the visit
        - casehistory (str): Patient's case history and symptoms
    
    Returns:
        JSON response containing:
        - result (dict): Full model response with diagnoses
        - conclusion (str): Summary conclusion from the model
        
    Status Codes:
        - 200: Success
        - 500: Internal server error or model service unavailable
    """
    request_data = request.get_json()
    loggerddx.info(f"Incoming request data: {json.dumps(request_data, indent=2)}")
    visitUUID = request_data['visitUuid']

    # Generate unique log ID for tracking
    log_id = str(uuid.uuid4())
    patient_case = request_data['casehistory']
    
    # Prepare request payload for AI model
    request_payload = {
        "model_name": os.environ.get('DDX_MODEL_NAME', 'gemini-2.0-flash'), 
        "case": patient_case, 
        "prompt_version": 1, 
        "tracker": log_id
    }
    loggerddx.info(f"Sending request to model: {json.dumps(request_payload, indent=2)}")

    # Log request to Elasticsearch for tracking
    es = Elasticsearch(os.environ.get('ELASTICSEARCH_URL', 'http://localhost:9200'))
    index_name = os.environ.get('DDX_INDEX_NAME', 'ddx_req')
    log_entry = {
        "timestamp": getCurrentDateTime(),
        "visitUUID": visitUUID
    }
    response_with_id = es.index(index=index_name, id=log_id, body=log_entry)

    try:
        # Call AI model service
        response = session.post(
            os.environ.get('DDX_MODEL_URL', 'http://127.0.0.1:5050/predict/v1'),
            json=request_payload
        )
        response.raise_for_status()

        # Log the response received
        loggerddx.info(f"Response status code: {response.status_code}")
        loggerddx.info(f"Response data: {json.dumps(response.json(), indent=2)}")

        # Prepare response
        rtnval = {}
        k2 = response.json()
        rtnval['result'] = k2
        rtnval['conclusion'] = k2["data"]["conclusion"]

        loggerddx.info(f"Returning response: {json.dumps(rtnval, indent=2)}")
        return make_response(jsonify(rtnval), 200)
    except requests.exceptions.RequestException as e:
        loggerddx.error(f"Request failed after retries: {str(e)}")
        rtnval = {'error': str(e)}
        return make_response(jsonify(rtnval), 500)

def rr(original_json):
    """
    Transforms diagnosis data from the original JSON format to the desired structured format.
    
    Args:
        original_json (dict): The original JSON data containing diagnosis information
        
    Returns:
        list: A list of dictionaries with diagnosis, rationale, and likelihood
    """
    try:
        # Extract the diagnosis and rationale text
        diagnosis_text = original_json["data"]["output"]["diagnosis"]
        rationale_text = original_json["data"]["output"]["rationale"]

        # Split the diagnosis into individual items
        diagnosis_items = [item.strip() for item in diagnosis_text.split("\n") if item.strip()]

        structured_output = []

        for i, diag in enumerate(diagnosis_items):
            # Extract diagnosis name and likelihood
            diag_parts = diag.split("(Likelihood: ")
            diagnosis_name = diag_parts[0].split(". ", 1)[1].strip()
            likelihood = diag_parts[1].rstrip(")").strip()
            
            # Find the corresponding rationale
            rationale_start = f"{i+1}. {diagnosis_name}"
            rationale_content = ""
            
            # Look for the rationale between current diagnosis and next one
            if i < len(diagnosis_items) - 1:
                next_diag = f"{i+2}. {diagnosis_items[i+1].split('. ', 1)[1].split('(Likelihood:')[0].strip()}"
                start_idx = rationale_text.find(rationale_start)
                end_idx = rationale_text.find(next_diag)
                if start_idx != -1 and end_idx != -1:
                    rationale_content = rationale_text[start_idx + len(rationale_start):end_idx].strip()
            else:
                start_idx = rationale_text.find(rationale_start)
                if start_idx != -1:
                    rationale_content = rationale_text[start_idx + len(rationale_start):].strip()
            
            # Clean up the rationale content
            rationale_content = rationale_content.replace("* **Rationale:**", "").strip()
            rationale_content = rationale_content.replace("* **Clinical Relevance and Features:**", "").strip()
            rationale_content = " ".join(rationale_content.split())  # Remove extra whitespace
            
            #extra cleanup
            rationale_content = rationale_content.replace("*","").strip()
            rationale_content = rationale_content[rationale_content.find("Clinical"):]
            # Create the diagnosis object
            diag_obj = {
                "diagnosis": diagnosis_name,
                "rationale": rationale_content,
                "likelihood": likelihood
            }
            
            structured_output.append(diag_obj)

        return structured_output

    except Exception as e:
        print(f"Error transforming diagnosis data: {str(e)}")
        return []


@app.route('/getdiags/<term>', methods=["GET"])
def getDiags(term):
    """
    Search SNOMED CT terminology for medical concepts.
    
    This endpoint searches the SNOMED CT terminology service for medical concepts
    matching the provided search term. It returns a filtered list of concepts
    with relevant clinical information.
    
    Args:
        term (str): Search term for medical concept (passed as URL parameter)
    
    Returns:
        JSON response containing:
        - result (list): List of matching SNOMED CT concepts
        
    Status Codes:
        - 200: Success
        - 500: Internal server error or terminology service unavailable
    """
    # URL encode the search term
    k = urllib.parse.quote(term)
    
    # Construct URL for SNOMED CT search
    urltocall = os.environ.get('SNOMED_BASE_URL') + '/csnoserv/api/search/search?term=' + k + '&state=active&acceptability=synonyms&fullconcept=false&returnlimit=-1'
    
    try:
        response = urlopen(urltocall)
        data = json.loads((response.read().decode('utf-8')))

        # Remove unnecessary fields from each concept
        for concept in data:
            concept.pop('conceptFsn', None)
            concept.pop('id', None)

        rtnval = {}
        rtnval['result'] = data
        return rtnval
    except Exception as e:
        loggerddx.error(f"Error searching SNOMED CT: {str(e)}")
        return make_response(jsonify({'error': 'Terminology service unavailable'}), 500)

def getCurrentDateTime():
    """
    Get current date and time in the configured timezone.
    
    Returns:
        str: Current date and time in format 'YYYY-MM-DD HH:MM:SS'
    """
    IST = pytz.timezone(os.environ.get('TIMEZONE', 'Asia/Calcutta'))
    utc_offset = mydt.now(IST).astimezone().strftime('%z')
    now = mydt.now().strftime("%Y-%m-%d %H:%M:%S")
    return now

def add_concept_reference_map(concept_id, concept_reference_term_id):
    """
    Add a concept reference map entry to link concepts with reference terms.
    
    This function creates a mapping between a concept and its reference term
    in the OpenMRS concept reference map table.
    
    Args:
        concept_id (int): The ID of the concept
        concept_reference_term_id (int): The ID of the concept reference term
    
    Returns:
        int: The ID of the created concept reference map entry
    """
    same_as = int(os.environ.get('CONCEPT_MAP_TYPE_ID', 1))
    concept_reference_map_insert_query = "INSERT INTO concept_reference_map(concept_reference_term_id, concept_map_type_id, creator, date_created, concept_id, uuid) VALUES (%s, %s, %s, %s, %s, %s)"
    insert_tuple_concept_reference_map = (concept_reference_term_id, same_as, int(os.environ.get('CONCEPT_CREATOR_ID', 1)), getCurrentDateTime(), concept_id, str(uuid.uuid4()))
    
    try:
        connection = mysql.connector.connect(host=os.environ.get('DB_HOST'),
                                         database=os.environ.get('DB_NAME'),
                                         user=os.environ.get('DB_USER'),
                                         password=os.environ.get('DB_PASSWORD'))
        cursor = connection.cursor(prepared=True)
        print(insert_tuple_concept_reference_map)
        cursor.execute(concept_reference_map_insert_query, insert_tuple_concept_reference_map)
        connection.commit()
        concept_reference_term_id = cursor.lastrowid
        cursor.close()
        connection.close()
    except mysql.connector.Error as error:
        print(error)
        print("parameterized query failed {}".format(error))
        print("Error on line {}".format(sys.exc_info()[-1].tb_lineno))
    return concept_reference_term_id

def add_concept_reference_term(snomedct_code):
    """
    Add a concept reference term to the database.
    
    This function creates a new concept reference term entry in the OpenMRS
    concept_reference_term table, typically for SNOMED CT codes.
    
    Args:
        snomedct_code (str): The SNOMED CT code for the concept
    
    Returns:
        int: The ID of the created concept reference term
    """
    concept_reference_term_insert_query = "INSERT INTO concept_reference_term(concept_source_id, code, creator, date_created, retired, uuid) VALUES (%s, %s, %s, %s, %s, %s)"
    insert_tuple_concept_reference_term = (int(os.environ.get('CONCEPT_SOURCE_ID', 1)), snomedct_code, int(os.environ.get('CONCEPT_CREATOR_ID', 1)), getCurrentDateTime(), int(os.environ.get('CONCEPT_RETIRED', 0)), str(uuid.uuid4()))
    
    try:
        connection = mysql.connector.connect(host=os.environ.get('DB_HOST'),
                                         database=os.environ.get('DB_NAME'),
                                         user=os.environ.get('DB_USER'),
                                         password=os.environ.get('DB_PASSWORD'))
        cursor = connection.cursor(prepared=True)
        cursor.execute(concept_reference_term_insert_query, insert_tuple_concept_reference_term)
        connection.commit()
        concept_reference_term_id = cursor.lastrowid
        cursor.close()
        connection.close()
    except mysql.connector.Error as error:
        print(error)
        print("parameterized query failed {}".format(error))
        print("Error on line {}".format(sys.exc_info()[-1].tb_lineno))
    return concept_reference_term_id



def add_concept_diagnosis_set(concept_id):
    """
    Add a concept to the diagnosis concept set.
    
    This function adds a concept to the general diagnosis concept set in OpenMRS,
    making it available for use in diagnosis workflows.
    
    Args:
        concept_id (int): The ID of the concept to add to the set
    
    Returns:
        str: Success indicator ("A")
    """
    concept_set = int(os.environ.get('CONCEPT_SET_ID', 160168))
    concept_set_insert_query = "INSERT INTO concept_set(concept_set , concept_id, creator, date_created,  uuid) VALUES ( %s, %s, %s, %s, %s)"
    insert_tuple_concept_set = (concept_set, concept_id, int(os.environ.get('CONCEPT_CREATOR_ID', 1)), getCurrentDateTime(),  str(uuid.uuid4()) )
    
    try:
        connection = mysql.connector.connect(host=os.environ.get('DB_HOST'),
                                         database=os.environ.get('DB_NAME'),
                                         user=os.environ.get('DB_USER'),
                                         password=os.environ.get('DB_PASSWORD'))
        cursor = connection.cursor(prepared=True)
        cursor.execute(concept_set_insert_query, insert_tuple_concept_set)
        connection.commit()
        cursor.close()
        connection.close()
    except mysql.connector.Error as error:
        print(error)
        print("parameterized query failed {}".format(error))
        print("Error on line {}".format(sys.exc_info()[-1].tb_lineno))

    return "A"
def add_concept_name(concept_id, concept_name):
    """
    Add a concept name to the database.
    
    This function creates a new concept name entry in the OpenMRS concept_name table,
    typically for the fully specified name of a concept.
    
    Args:
        concept_id (int): The ID of the concept
        concept_name (str): The name of the concept
    
    Returns:
        str: Success indicator ("A")
    """
    locale = os.environ.get('CONCEPT_LOCALE', 'en')
    concept_name_insert_query = "INSERT INTO concept_name (concept_id, name, locale, creator, date_created, voided, uuid, concept_name_type) VALUES(%s, %s, %s, %s, %s, %s, %s, %s)"
    insert_tuple_concept_name = (concept_id, concept_name, locale, int(os.environ.get('CONCEPT_CREATOR_ID', 1)), getCurrentDateTime(), 0, str(uuid.uuid4()), os.environ.get('CONCEPT_NAME_TYPE', 'FULLY_SPECIFIED'))
    
    try:
        connection = mysql.connector.connect(host=os.environ.get('DB_HOST'),
                                         database=os.environ.get('DB_NAME'),
                                         user=os.environ.get('DB_USER'),
                                         password=os.environ.get('DB_PASSWORD'))
        cursor = connection.cursor(prepared=True)
        cursor.execute(concept_name_insert_query, insert_tuple_concept_name)
        connection.commit()
        cursor.close()
        connection.close()
    except mysql.connector.Error as error:
        print(error)
        print("parameterized query failed {}".format(error))
        print("Error on line {}".format(sys.exc_info()[-1].tb_lineno))

    return "A"


def add_concept():
    """
    Create a new concept in the database.
    
    This function creates a new concept entry in the OpenMRS concept table
    with default values for class, datatype, and other properties.
    
    Returns:
        int: The ID of the created concept
    """
    concept_uuid = str(uuid.uuid4())
    n_a = int(os.environ.get('CONCEPT_DATATYPE_ID', 4))
    retired = int(os.environ.get('CONCEPT_RETIRED', 0))
    is_set = int(os.environ.get('CONCEPT_IS_SET', 0))
    class_id = int(os.environ.get('CONCEPT_CLASS_ID', 4))
    creator = int(os.environ.get('CONCEPT_CREATOR_ID', 1))
    
    try:
        connection = mysql.connector.connect(host=os.environ.get('DB_HOST'),
                                         database=os.environ.get('DB_NAME'),
                                         user=os.environ.get('DB_USER'),
                                         password=os.environ.get('DB_PASSWORD'))
        cursor = connection.cursor(prepared=True)
        concept_insert_query = (" INSERT INTO concept "
                       " (class_id, datatype_id, retired, is_set, creator,  date_created, uuid)  "
                       " VALUES (%s, %s, %s, %s, %s,  %s, %s)")

        insert_tuple_concept = (class_id, n_a, retired, is_set, creator, getCurrentDateTime(), concept_uuid)

        cursor.execute(concept_insert_query, insert_tuple_concept)
        connection.commit()
        concept_id = cursor.lastrowid
        cursor.close()
        connection.close()
    except mysql.connector.Error as error:
        print(error)
        print("parameterized query failed {}".format(error))
        print("Error on line {}".format(sys.exc_info()[-1].tb_lineno))
    return concept_id


def check_concept(concept_name):
    """
    Check if a concept exists in the database.
    
    This function searches for a concept by name in the OpenMRS concept_name table
    and returns the concept ID if found.
    
    Args:
        concept_name (str): The name of the concept to search for
    
    Returns:
        int: The concept ID if found, 0 if not found
    """
    try:
        connection = mysql.connector.connect(host=os.environ.get('DB_HOST'),
                                         database=os.environ.get('DB_NAME'),
                                         user=os.environ.get('DB_USER'),
                                         password=os.environ.get('DB_PASSWORD'))
        cursor = connection.cursor(prepared=True)
        concept_check_query = (" SELECT IFNULL(concept_id,0) AS cnt FROM concept_name WHERE lower(name) = lower(%s) AND concept_name_type ='FULLY_SPECIFIED' AND locale='en' ")
        tuple_concept = (concept_name,)
        cursor.execute(concept_check_query, tuple_concept)
        r = cursor.fetchone()
        print(r)
        cursor.close()
        connection.close()

        if r is None:
            return 0
    except mysql.connector.Error as error:
        print(error)
        print("parameterized query failed {}".format(error))
        print("Error on line {}".format(sys.exc_info()[-1].tb_lineno))
    return r[0]



@app.route('/snomed', methods=["POST"])
def snomed():
    """
    Manage SNOMED CT concept mappings in the database.
    
    This endpoint either creates a new concept with SNOMED CT mapping or adds
    SNOMED CT mapping to an existing concept. It handles the complete workflow
    of concept creation, naming, and reference term mapping.
    
    Request Body:
        JSON object containing:
        - conceptName (str): The name of the medical concept
        - snomedCode (str): The SNOMED CT code for the concept
    
    Returns:
        JSON response containing:
        - result (str): Success message describing the action taken
        
    Status Codes:
        - 200: Success
        - 500: Internal server error or database error
    """
    request_data = request.get_json()
    concept_name = request_data['conceptName']
    snomed_code = request_data['snomedCode']
    rtnval = {}
    res = ""
    
    # Check if concept already exists
    result = check_concept(concept_name)
    if result > 0:
        # Concept exists, add SNOMED CT mapping
        k = add_concept_reference_term(snomed_code)
        y = add_concept_reference_map(result, k)
        res = "SNOMED CT Mapping added for diagnosis {}".format(concept_name)
    else:
        # Concept doesn't exist, create new concept with mapping
        concept_id = add_concept()
        add_concept_name(concept_id, concept_name)
        crt_id = add_concept_reference_term(snomed_code)
        add_concept_reference_map(concept_id, crt_id)
        add_concept_diagnosis_set(concept_id)
        res = "Diagnosis {} is created with Concept ID {} ".format(concept_name, concept_id)
    
    rtnval['result'] = res
    return rtnval


@app.route('/ttxv1', methods=["POST"])
def ttxv1():
    """
    Generate treatment recommendations using AI model.
    
    This endpoint processes patient case history and diagnosis to generate
    treatment recommendations including medications, dosages, and clinical guidance.
    
    Request Body:
        JSON object containing:
        - visitUuid (str): Unique identifier for the visit
        - case (str): Patient's case history and symptoms
        - diagnosis (str): The primary diagnosis for treatment planning
    
    Returns:
        JSON response containing:
        - result (dict): Full model response with treatment recommendations
        
    Status Codes:
        - 200: Success
        - 400: Validation error
        - 500: Internal server error or model service unavailable
    """
    rtnval = {}
    request_data = request.get_json()
    
    loggerttx.info(f"Incoming request ttx data: {json.dumps(request_data, indent=2)}")
    
    visitUUID = request_data['visitUuid']
    log_id = str(uuid.uuid4())
    
    # Log request to Elasticsearch for tracking
    es = Elasticsearch(os.environ.get('ELASTICSEARCH_URL', 'http://localhost:9200'))
    index_name = os.environ.get('TTX_INDEX_NAME', 'ttx_req')
    log_entry = {
        "timestamp": getCurrentDateTime(),
        "visitUUID": visitUUID
    }
    response_with_id = es.index(index=index_name, id=log_id, body=log_entry)

    # Prepare request payload for AI model
    request_payload = {
        "model_name": os.environ.get('TTX_MODEL_NAME', 'gemini-2.5-flash-preview-04-17'),
        "case": request_data['case'],
        "diagnosis": request_data['diagnosis'],
        "tracker": log_id
    }
    
    loggerttx.info(f"ttx- Sending request to model: {json.dumps(request_payload, indent=2)}")
    
    # Get URL from environment variable or use default
    model_url = os.environ.get('TTX_MODEL_URL', 'http://127.0.0.1:5051/ttx/v1')
    
    try:
        response = requests.post(
            model_url,
            json=request_payload
        )
        response.raise_for_status()
        
        # Log the response received
        loggerttx.info(f"ttx- Response status code: {response.status_code}")
        loggerttx.info(f"ttx- Response data: {json.dumps(response.json(), indent=2)}")
        
        response_data = response.json()
        rtnval['result'] = response_data
        
        loggerttx.info(f"ttx- Returning response: {json.dumps(rtnval, indent=2)}")
        return make_response(jsonify(rtnval), 200)
        
    except ValueError as e:
        loggerttx.error(f"ttx- Validation error: {str(e)}")
        rtnval['error'] = str(e)
        return make_response(jsonify(rtnval), 400)
    except requests.exceptions.RequestException as e:
        loggerttx.error(f"ttx- Request failed: {str(e)}")
        rtnval['error'] = str(e)
        return make_response(jsonify(rtnval), 500)
    except Exception as e:
        loggerttx.error(f"ttx- Unexpected error: {str(e)}")
        rtnval['error'] = "Internal server error"
        return make_response(jsonify(rtnval), 500)


if __name__ == "__main__":
    """
    Main execution block for the Flask application.
    
    Starts the Flask development server with configuration from environment variables.
    The server will listen on all interfaces (0.0.0.0) by default.
    """
    app.run(host=os.environ.get('FLASK_HOST', '0.0.0.0'))

