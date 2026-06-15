import sqlite3
import json
import logging
from dataclasses import dataclass
from typing import List, Dict, Optional
import spacy

logger = logging.getLogger(__name__)

try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    logger.warning("SpaCy model 'en_core_web_sm' not found. Attempting to download...")
    from spacy.cli.download import download
    download("en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")

@dataclass
class Triplet:
    subject: str
    predicate: str
    object: str

class KnowledgeGraph:
    def __init__(self, conn: Optional[sqlite3.Connection] = None, db_path: str = "memory.db"):
        if conn is not None:
            self.conn = conn
            self._owns_conn = False
        else:
            self.conn = sqlite3.connect(db_path, check_same_thread=False)
            self._owns_conn = True
        self._init_db()

    def _init_db(self):
        cursor = self.conn.cursor()
        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS Entities (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE,
                type TEXT                 
            );
            CREATE TABLE IF NOT EXISTS Triplets(
                subject_id INTEGER,
                predicate TEXT,
                object_id INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(subject_id) REFERENCES Entities(id),
                FOREIGN KEY(object_id) REFERENCES Entities(id)
            );
            CREATE INDEX IF NOT EXISTS idx_entities_name ON Entities(name);
            CREATE INDEX IF NOT EXISTS idx_triplets_subject ON Triplets(subject_id);
            CREATE INDEX IF NOT EXISTS idx_triplets_object ON Triplets(object_id);
        """
        )
        self.conn.commit()

    def add_knowledge(self, facts: List[Dict[str, str]]):
        """Add facts to the knowledge graph. 
        
        Args:
            facts: List of dictionaries with 's', 'p', 'o' keys.
        """
        cursor = self.conn.cursor()
        added_count = 0
        for fact in facts:
            triplet = self._parse_fact_to_triplet(fact)
            if triplet:
                subject_id = self._get_or_create_entity(cursor, triplet.subject.lower())
                object_id = self._get_or_create_entity(cursor, triplet.object.lower())

                cursor.execute(
                    """
                        SELECT 1 FROM Triplets
                        WHERE subject_id = ? AND predicate = ? AND object_id = ?
                    """, (subject_id, triplet.predicate, object_id)
                )

                if not cursor.fetchone():
                    cursor.execute(
                        """
                            INSERT INTO Triplets (subject_id, predicate, object_id)
                            VALUES (?, ?, ?)
                        """, (subject_id, triplet.predicate, object_id)
                    )
                    added_count += 1

        self.conn.commit()
        logger.info(f"Added {added_count} new facts to the knowledge graph.")

    def _parse_fact_to_triplet(self, fact: Dict[str, str]) -> Optional[Triplet]:
        try:
            subject = str(fact["s"]).strip()
            predicate = str(fact["p"]).strip()
            object_ = str(fact["o"]).strip()

            if subject and predicate and object_:
                return Triplet(subject, predicate, object_)
        except KeyError as e:
            logger.error(f"Error parsing fact: {fact}. Error: {e}")
            return None
        
    def _get_or_create_entity(self, cursor: sqlite3.Cursor, name: str) -> Optional[int]:
        cursor.execute("SELECT id FROM Entities WHERE name = ?", (name,))
        result = cursor.fetchone()
        if result:
            return result[0]
        cursor.execute("INSERT INTO Entities (name, type) VALUES (?, ?)", (name, "unknown"))
        return cursor.lastrowid
    
    def _extract_keywords(self, text: str) -> List[str]:
        doc = nlp(text)
        keywords = set()

        for ent in doc.ents:
            keywords.add(ent.text.lower())

        for token in doc:
            if token.pos_ in ["NOUN", "PROPN"]:
                keywords.add(token.text.lower())

        return list(keywords)

    def get_relevant_facts(self, prompt: str) -> str:
        """Find facts in the DB relevant to the nouns/entities in the user prompt."""

        keywords = self._extract_keywords(prompt)
        if not keywords:
            return ""
        
        cursor = self.conn.cursor()
        relevant_triplets = set()

        for kw in keywords:
            search_term = f"%{kw}%"

            cursor.execute(
                """
                    SELECT s.name, t.predicate, o.name
                    FROM Triplets t
                    JOIN Entities s ON t.subject_id = s.id
                    JOIN Entities o ON t.object_id = o.id
                    WHERE s.name LIKE ? OR o.name LIKE ?
                    ORDER BY t.timestamp DESC
                    LIMIT 10
                """, (search_term, search_term)
            )

            for row in cursor.fetchall():
                relevant_triplets.add((row[0], row[1], row[2]))

        if not relevant_triplets:
            return ""
        
        return "\n".join([f"{s} {p} {o}" for s, p, o in relevant_triplets])

    def query_entity(self, name: str, limit: int = 50) -> List[Dict[str, str]]:
        """Return all triplets where the entity appears as subject or object."""
        name_lower = name.lower()
        cursor = self.conn.cursor()
        cursor.execute(
            """
                SELECT s.name, t.predicate, o.name
                FROM Triplets t
                JOIN Entities s ON t.subject_id = s.id
                JOIN Entities o ON t.object_id = o.id
                WHERE s.name = ? OR o.name = ?
                ORDER BY t.timestamp DESC
                LIMIT ?
            """, (name_lower, name_lower, limit)
        )
        return [
            {"subject": row[0], "predicate": row[1], "object": row[2],
             "confidence": 1.0, "source": "stored"}
            for row in cursor.fetchall()
        ]

    def close(self):
        """Close the connection only if this instance owns it."""
        if self._owns_conn:
            self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False