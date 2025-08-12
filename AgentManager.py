import os
import sqlite3
import google.generativeai as genai
import qdrant_client
import pandas as pd
from qdrant_client import QdrantClient
from langchain_community.vectorstores import Qdrant
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

class AgentManager:
    def __init__(
        self,
        llm_model_name: str = 'gemini-2.5-flash',
        api_key: str = GEMINI_API_KEY,
        database_path: str = '/Users/owenjung/Downloads/adept current aug6 noon.db',
        qdrant_url: str = 'http://localhost:6333',
        collection_name: str = 'adept_database',
        query: str = 'No prompt entered.',
        embedding_model: str = "BAAI/bge-small-en"

    ):
        
        self.llm_model_name = llm_model_name
        self.api_key = api_key
        self.database_path = database_path
        self.qdrant_url = qdrant_url
        self.collection_name = collection_name
        self.query = query
        self.embedding_model = embedding_model

        # Initialize Embeddings
        self.embeddings = SentenceTransformer(self.embedding_model)
        # Embed the query in the same embeddings as 
        self.query_vector = self.embeddings.encode(self.query, convert_to_numpy=True)

        # Initialize Qdrant client
        self.qdrant_client = QdrantClient(host="localhost", port=6333)

        # Initialize the Qdrant vector store
        self.qdrant = Qdrant(
            client=self.qdrant_client,
            embeddings=self.embeddings,
            collection_name=self.collection_name
        )


        # Generate LLM API call
        self.llm_client = genai.configure(api_key = self.api_key)
        self.model = genai.GenerativeModel(self.llm_model_name)

    # Helper function which grabs pragma and contents for a single table from SQL
    def get_table_schema(self, table_name: str):
        to_return = {}
        with sqlite3.connect(self.database_path) as conn:
            cursor = conn.cursor()
            # pragma gives (cid, name, type, notnull, dflt_value, pk)
            cursor.execute(f'PRAGMA table_info("{table_name}")')
            to_return['Schema'] = cursor.fetchall()

            df = pd.read_sql_query(f'SELECT * FROM "{table_name}"', conn)
            to_return['Rows'] = df
        return to_return

    # Function which specifically gets routing tables returned by agent
    def get_sql_routing_schemas(self, table_dict: dict):
        routing_tables = {}
        
        if 'SQL' not in table_dict or not table_dict['SQL']:
            print("Dictionary doesn't contain SQL sources")
            return routing_tables
        table_list = table_dict['SQL']

        for table in table_list:
            table_schema = self.get_table_schema(table)

            schema = table_schema['Schema']  # list of (cid, name, type, ...)
            col_names = [c[1] for c in schema]
            rows = table_schema['Rows']
            
            key_col = col_names.index('table_name') # Column table_names is the one to grab
            inner = {}  
            for _, row in rows.iterrows():
                key = row.iloc[key_col]
                inner[key] = row
      
            routing_tables[table] = inner
        
        return routing_tables

    def get_qdrant_routing_schemas(self, table_dict: dict):
        routing_tables = {}
        
        if 'Qdrant' not in table_dict or not table_dict['Qdrant']:
            print("Dictionary doesn't contain Qdrant sources")
            return routing_tables

        table_list = table_dict['Qdrant']

        for table in table_list:
            table_schema = self.get_table_schema(table)

            schema = table_schema['Schema']  # list of (cid, name, type, ...)
            col_names = [c[1] for c in schema]
            rows = table_schema['Rows']
            
            key_col = col_names.index('qdrant_point_id') # Column table_names is the one to grab
            inner = {}  
            for _, row in rows.iterrows():
                key = row.iloc[key_col]
                inner[key] = row
      
            routing_tables[table] = inner

    # Semantic search QDrant database for top_k most similar sources to prompt
    def search_qdrant(self, top_k=10, filter_sources=None):
        must_filters = []
        if filter_sources:
            must_filters.append({
                "key": "source",
                "match": {"any": filter_sources}
            })

        return self.qdrant_client.query_points(
            collection_name=self.collection_name,
            query= self.query_vector,
            limit=top_k
        )
    

    def open_databases(self, relevant_tables: dict):
        # Connect to Database
        qdrant_list = relevant_tables["QDrant"]
        sql_list = relevant_tables["SQL"]
        print(f"qdrant list: {qdrant_list}")
        conn= sqlite3.connect(self.database_path)
        detail_tables = {}

        # Open each database in the list of relevant databases and then add it to the output dictionary
        for db_name in sql_list:
            df = pd.read_sql_query(f"SELECT * FROM {db_name}", conn)
            detail_tables[db_name] = df

        conn.close()
        for qdrant_id in qdrant_list:
            detail_tables[qdrant_id] = self.qdrant_client.query_points(
                                                collection_name=self.collection_name,
                                                query= qdrant_id,
                                            )

        return detail_tables

    # This function has the LLM return a list of relevant sources
    def get_master_response(self):
        master_schema = self.get_table_schema(table_name='Master')
        prompt = self.query

        master_response = self.model.generate_content(
        f"""You are a SQLITE expert, tasked with retrieval from a database of public Kenyan information. The data is organized in a Master-Detail 
        format, with the first Master table being as follows: {master_schema}. You have a user who has given you the following prompt: {prompt}.

        Using information from the columns Summary and Sections, create a list of tables from the column table_name that might contain data relevant to the user's question.
        There is no limit on the amount of tables you want to retrieve; only reject tables if it's highly unlikely that they contain relevant information.
        Return at least one table of datatype SQL and at least one of datatype QDrant. 

        Return the table_names in the following format, separated by commas with no spaces, and return nothing else:
        table_a,table_b,table_c
        """
        )
        
        table_list = master_response.text.split(',')
        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()
        result_dict = {}

        for table in table_list:
            cursor.execute("SELECT Datatype FROM Master WHERE table_name = ?", (table,))
            row = cursor.fetchone()  # single row
            if row:  # if a match was found
                datatype_str = row[0]  # extract the string value
                result_dict.setdefault(datatype_str, []).append(table)

        conn.close()

        return result_dict
    
    # This has the function return a list of relevant individual tables and qdrant points from the two databases. 
    def get_routing_response(self, qdrant_dict, sql_dict):
        prompt = self.query
        qdrant_sources = qdrant_dict
        sql_sources = sql_dict
        sql_response = self.model.generate_content(
            f"""You are a SQLite expert, tasked with retrieval from a database of public Kenyan information.

            The SQL tables that point to SQL details you may access are as following: {sql_sources}.

            Your primary goal is to write sqlite commands to find and return relevant tables to the client's prompt, completely unaltered. 
            Use the routing tables (using Title and sectors, along with any other inferences you might make) to find individual tables
            (dictionary keys) that are relevant to the prompt. Return these (find 5-10 sources)
            table_names as a list, openable with SQLite, putting the most relevant tables first.

            Once you have found these sources, return them in list format, without any additional text. Tables should be in the
            following format: table_a,table_b,table_c,table_d so that they can be split by str.split(',').

            Return only the comma-separated list, and nothing else. 

            The client's prompt is as follows: {prompt}. When reading this client's prompt, think about what sectors might be relevant to them and what kind of data they might be looking for within that sector.
            """
        )
        if qdrant_dict:
            qdrant_response = self.model.generate_content(
                f"""You are a SQLite expert, tasked with retrieval from a database of public Kenyan information.

                The SQL tables that point to Qdrant point IDs you may access are as following: {qdrant_sources}.

                Your primary goal is to write sqlite commands to find and return relevant QDrant chunks to the client's prompt, completely unaltered. 
                Use the given tables to find individual QDrant point IDs
                (dictionary keys) that are relevant to the prompt. Return these (find 3-5 sources)
                qdrant_point_ids as a list, openable with SQLite, putting the most relevant tables first.

                Once you have found these sources, return them in list format, without any additional text. Tables should be in the
                following format: point_a,point_b,point_c,point_d so that they can be split by str.split(',').

                Return only the comma-separated list, and nothing else. 

                The client's prompt is as follows: {prompt}. When reading this client's prompt, think about what information might be relevant and what kind of data they might be looking for within that chunk.
                """
            )
        else:
            qdrant_response = ""

        
        to_return = {}
        if sql_response:
            sql_list = sql_response.text.split(',')
        if qdrant_response:
            qdrant_list = qdrant_response.text.split('')
        else:
            qdrant_list = []

        print('SQL Tables: ')
        print(sql_list)

        print('\n QDrant Point IDs: ')
        print(qdrant_list)

        to_return['SQL'] = sql_list
        to_return['QDrant'] = qdrant_list

        return to_return
    
    def get_final_response(self, qdrant_results, detail_tables):
        query = self.query
        final_response = self.model.generate_content(
            f"""You are a SQLite expert, tasked with retrieval from a database of public Kenyan information.

            You have already received a client's prompt and returned the following dictionary of relevant tables and text chunks: {detail_tables}. Also, you have received
            the following list of QDrant-stored text chunks via RAG: {qdrant_results}.
            The prompt was as follows: {query}. Return the relevant SQL tables'
            table master and detail IDs, along with the corresponding table_name and Title from the routing table, at the top of your response, allowing me to go into the database and find those tables myself, putting the most relevant tables first.

            After this return, I want a paragraph of relevant information and some insight sourced from within the detail tables you found. Include SQLite commands to the data you cite as parenthetical sources, so that we can go into the tables ourselves
            and check the data. In this paragraph, make sure to be accurate with units. In this paragraph, attempt to combine multiple insights to tell coherent 'stories' pertaining to the client's request.
            When coming up with your advice, be completely honest, with no bias towards what the client seems to want. However, even if you think that one course of direction makes lots of sense, be sure to include at least one piece of evidence
            against that course of action, in order to paint the most transparent picture.

            Finally, suggest one or two more potential avenues of research for the client."""
        )
        response_text = final_response.text
        print(response_text)

        return 

    def pipeline(self):
        qdrant_search = self.search_qdrant(top_k = 10)

        master_dict = self.get_master_response()

        sql_routing = self.get_sql_routing_schemas(table_dict=master_dict)
        qdrant_routing = self.get_qdrant_routing_schemas(table_dict=master_dict)

        routing_response = self.get_routing_response(qdrant_dict=qdrant_routing, sql_dict=sql_routing)

        sql_list = routing_response['SQL']
        qdrant_list = routing_response["QDrant"]

        detail_tables = self.open_databases(routing_response)

        final_response = self.get_final_response(qdrant_results=qdrant_search, detail_tables = detail_tables)

        
        to_return = {}

        to_return['text']= final_response
        to_return['sql_list']=sql_list
        to_return['qdrant_list']=qdrant_list
        to_return['qdrant_search']=qdrant_search


manager = AgentManager(query="I'm a farmer in Limuru and want to explore selling my excess maize stock. How might I go about doing that and am i in the right location?")
output = manager.pipeline()

