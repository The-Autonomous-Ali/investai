// InvestAI — Knowledge Graph Seed Data
// Run this in Neo4j Browser after startup: 
//   CALL apoc.cypher.runFile('/var/lib/neo4j/import/seed.cypher')

// ── Clear existing data ──────────────────────────────────────────────────────
MATCH (n) DETACH DELETE n;

// ── Create Event Types ───────────────────────────────────────────────────────
CREATE (:EventType {name: 'Geopolitical',      id: 'geo'})
CREATE (:EventType {name: 'Monetary Policy',   id: 'monetary'})
CREATE (:EventType {name: 'Commodity',         id: 'commodity'})
CREATE (:EventType {name: 'Currency',          id: 'currency'})
CREATE (:EventType {name: 'Fiscal',            id: 'fiscal'})
CREATE (:EventType {name: 'Natural Disaster',  id: 'natural'})
CREATE (:EventType {name: 'Corporate',         id: 'corporate'});

// ── Create Key Events (Templates) ───────────────────────────────────────────
CREATE (:Event {name: 'Oil Price Spike',          type: 'commodity',   typical_duration: 'medium_term'})
CREATE (:Event {name: 'Oil Price Crash',          type: 'commodity',   typical_duration: 'medium_term'})
CREATE (:Event {name: 'Middle East Conflict',     type: 'geo',         typical_duration: 'medium_term'})
CREATE (:Event {name: 'Strait of Hormuz Risk',    type: 'geo',         typical_duration: 'short_term'})
CREATE (:Event {name: 'RBI Rate Hike',            type: 'monetary',    typical_duration: 'long_term'})
CREATE (:Event {name: 'RBI Rate Cut',             type: 'monetary',    typical_duration: 'long_term'})
CREATE (:Event {name: 'RBI Rate Hold',            type: 'monetary',    typical_duration: 'medium_term'})
CREATE (:Event {name: 'INR Depreciation',         type: 'currency',    typical_duration: 'medium_term'})
CREATE (:Event {name: 'INR Appreciation',         type: 'currency',    typical_duration: 'medium_term'})
CREATE (:Event {name: 'FII Selling',              type: 'currency',    typical_duration: 'short_term'})
CREATE (:Event {name: 'FII Buying',               type: 'currency',    typical_duration: 'short_term'})
CREATE (:Event {name: 'US Fed Rate Hike',         type: 'monetary',    typical_duration: 'long_term'})
CREATE (:Event {name: 'Global Recession Risk',    type: 'geo',         typical_duration: 'long_term'})
CREATE (:Event {name: 'India Election',           type: 'fiscal',      typical_duration: 'long_term'})
CREATE (:Event {name: 'India GDP Beat',           type: 'fiscal',      typical_duration: 'long_term'})
CREATE (:Event {name: 'India Inflation Rise',     type: 'monetary',    typical_duration: 'medium_term'})
CREATE (:Event {name: 'Monsoon Failure',          type: 'natural',     typical_duration: 'medium_term'})
CREATE (:Event {name: 'DXY Strengthening',        type: 'currency',    typical_duration: 'medium_term'})
CREATE (:Event {name: 'Global Risk Off',          type: 'geo',         typical_duration: 'short_term'});

// ── Create India Sectors ─────────────────────────────────────────────────────
CREATE (:Sector {name: 'Aviation',        country: 'India', nse_index: 'NIFTYAUTO'})
CREATE (:Sector {name: 'Oil & Gas',       country: 'India', nse_index: 'NIFTYENERGY'})
CREATE (:Sector {name: 'Paints',          country: 'India', instruments: ['ASIANPAINT', 'BERGER', 'KANSAINER']})
CREATE (:Sector {name: 'Tyres',           country: 'India', instruments: ['MRF', 'APOLLOTYRE', 'BALKRISIND']})
CREATE (:Sector {name: 'FMCG',            country: 'India', nse_index: 'NIFTYFMCG'})
CREATE (:Sector {name: 'Banking',         country: 'India', nse_index: 'NIFTYBANK'})
CREATE (:Sector {name: 'IT',              country: 'India', nse_index: 'NIFTYIT'})
CREATE (:Sector {name: 'Real Estate',     country: 'India', nse_index: 'NIFTYREALTY'})
CREATE (:Sector {name: 'Infrastructure',  country: 'India', nse_index: 'NIFTYINFRA'})
CREATE (:Sector {name: 'Pharma',          country: 'India', nse_index: 'NIFTYPHARMA'})
CREATE (:Sector {name: 'Auto',            country: 'India', nse_index: 'NIFTYAUTO'})
CREATE (:Sector {name: 'Metals',          country: 'India', nse_index: 'NIFTYMETAL'})
CREATE (:Sector {name: 'Renewable Energy',country: 'India', instruments: ['ADANIGREEN', 'TATAPOWER']})
CREATE (:Sector {name: 'Defence',         country: 'India', instruments: ['HAL', 'BEL', 'BHEL']})
CREATE (:Sector {name: 'Gold',            country: 'India', instruments: ['GOLDBEES', 'SGBMAR29']})
CREATE (:Sector {name: 'NBFC',            country: 'India', instruments: ['BAJFINANCE', 'MUTHOOTFIN']});

// ── Create Cause-Effect Relationships ────────────────────────────────────────

// Oil Price Spike chains
MATCH (e:Event {name:'Oil Price Spike'}), (s:Sector {name:'Aviation'})
CREATE (e)-[:CAUSES {strength:0.87, avg_lag_days:7,  direction:'negative', instances:5, confidence:'high'}]->(s);

MATCH (e:Event {name:'Oil Price Spike'}), (s:Sector {name:'Paints'})
CREATE (e)-[:CAUSES {strength:0.72, avg_lag_days:14, direction:'negative', instances:5, confidence:'high'}]->(s);

MATCH (e:Event {name:'Oil Price Spike'}), (s:Sector {name:'Tyres'})
CREATE (e)-[:CAUSES {strength:0.68, avg_lag_days:14, direction:'negative', instances:4, confidence:'medium'}]->(s);

MATCH (e:Event {name:'Oil Price Spike'}), (s:Sector {name:'Oil & Gas'})
CREATE (e)-[:CAUSES {strength:0.91, avg_lag_days:1,  direction:'positive', instances:6, confidence:'high'}]->(s);

MATCH (e:Event {name:'Oil Price Spike'}), (s:Sector {name:'FMCG'})
CREATE (e)-[:CAUSES {strength:0.55, avg_lag_days:30, direction:'negative', instances:4, confidence:'medium'}]->(s);

// Middle East → Oil chain
MATCH (e1:Event {name:'Middle East Conflict'}), (e2:Event {name:'Oil Price Spike'})
CREATE (e1)-[:CAUSES {strength:0.75, avg_lag_days:3, confidence:'medium'}]->(e2);

MATCH (e1:Event {name:'Middle East Conflict'}), (e2:Event {name:'Strait of Hormuz Risk'})
CREATE (e1)-[:CAUSES {strength:0.60, avg_lag_days:1, confidence:'medium'}]->(e2);

MATCH (e1:Event {name:'Strait of Hormuz Risk'}), (e2:Event {name:'Oil Price Spike'})
CREATE (e1)-[:CAUSES {strength:0.85, avg_lag_days:1, confidence:'high'}]->(e2);

// RBI Rate chains
MATCH (e:Event {name:'RBI Rate Hike'}), (s:Sector {name:'Real Estate'})
CREATE (e)-[:CAUSES {strength:0.82, avg_lag_days:30, direction:'negative', instances:4, confidence:'high'}]->(s);

MATCH (e:Event {name:'RBI Rate Hike'}), (s:Sector {name:'NBFC'})
CREATE (e)-[:CAUSES {strength:0.75, avg_lag_days:14, direction:'negative', instances:4, confidence:'high'}]->(s);

MATCH (e:Event {name:'RBI Rate Cut'}), (s:Sector {name:'Real Estate'})
CREATE (e)-[:CAUSES {strength:0.80, avg_lag_days:30, direction:'positive', instances:3, confidence:'high'}]->(s);

MATCH (e:Event {name:'RBI Rate Cut'}), (s:Sector {name:'Banking'})
CREATE (e)-[:CAUSES {strength:0.65, avg_lag_days:7,  direction:'negative', instances:3, confidence:'medium', note:'NIM compression'}]->(s);

// INR chains
MATCH (e:Event {name:'INR Depreciation'}), (s:Sector {name:'IT'})
CREATE (e)-[:CAUSES {strength:0.76, avg_lag_days:1, direction:'positive', instances:8, confidence:'high', note:'USD revenue boost in INR terms'}]->(s);

MATCH (e:Event {name:'INR Depreciation'}), (s:Sector {name:'Pharma'})
CREATE (e)-[:CAUSES {strength:0.60, avg_lag_days:7, direction:'positive', instances:6, confidence:'medium', note:'Export earnings boost'}]->(s);

// Oil → INR chain
MATCH (e1:Event {name:'Oil Price Spike'}), (e2:Event {name:'INR Depreciation'})
CREATE (e1)-[:CAUSES {strength:0.78, avg_lag_days:7, confidence:'high', note:'CAD widening pressure'}]->(e2);

// USD strengthening → INR
MATCH (e1:Event {name:'DXY Strengthening'}), (e2:Event {name:'INR Depreciation'})
CREATE (e1)-[:CAUSES {strength:0.72, avg_lag_days:2, confidence:'high'}]->(e2);

// FII Selling chains
MATCH (e:Event {name:'FII Selling'}), (s:Sector {name:'Banking'})
CREATE (e)-[:CAUSES {strength:0.70, avg_lag_days:1, direction:'negative', instances:10, confidence:'high'}]->(s);

// Global Risk Off
MATCH (e1:Event {name:'Global Risk Off'}), (e2:Event {name:'FII Selling'})
CREATE (e1)-[:CAUSES {strength:0.80, avg_lag_days:1, confidence:'high'}]->(e2);

MATCH (e1:Event {name:'Global Recession Risk'}), (e2:Event {name:'Global Risk Off'})
CREATE (e1)-[:CAUSES {strength:0.85, avg_lag_days:7, confidence:'high'}]->(e2);

// Gold as hedge
MATCH (e:Event {name:'Global Risk Off'}), (s:Sector {name:'Gold'})
CREATE (e)-[:CAUSES {strength:0.78, avg_lag_days:1, direction:'positive', instances:8, confidence:'high', note:'Safe haven demand'}]->(s);

MATCH (e:Event {name:'India Inflation Rise'}), (s:Sector {name:'Gold'})
CREATE (e)-[:CAUSES {strength:0.65, avg_lag_days:30, direction:'positive', instances:5, confidence:'medium', note:'Inflation hedge'}]->(s);

// Monsoon chains
MATCH (e:Event {name:'Monsoon Failure'}), (s:Sector {name:'FMCG'})
CREATE (e)-[:CAUSES {strength:0.65, avg_lag_days:45, direction:'negative', instances:3, confidence:'medium', note:'Rural demand falls'}]->(s);

MATCH (e:Event {name:'Monsoon Failure'}), (s:Sector {name:'Auto'})
CREATE (e)-[:CAUSES {strength:0.58, avg_lag_days:60, direction:'negative', instances:3, confidence:'medium', note:'Rural auto sales fall'}]->(s);

// GDP Beat
MATCH (e:Event {name:'India GDP Beat'}), (s:Sector {name:'Infrastructure'})
CREATE (e)-[:CAUSES {strength:0.70, avg_lag_days:7, direction:'positive', instances:4, confidence:'medium'}]->(s);

MATCH (e:Event {name:'India GDP Beat'}), (s:Sector {name:'Banking'})
CREATE (e)-[:CAUSES {strength:0.65, avg_lag_days:7, direction:'positive', instances:4, confidence:'medium', note:'Credit growth expectations'}]->(s);

// Election
MATCH (e:Event {name:'India Election'}), (s:Sector {name:'Infrastructure'})
CREATE (e)-[:CAUSES {strength:0.72, avg_lag_days:180, direction:'positive', instances:3, confidence:'medium', note:'Pre-election spending surge'}]->(s);

MATCH (e:Event {name:'India Election'}), (s:Sector {name:'Defence'})
CREATE (e)-[:CAUSES {strength:0.68, avg_lag_days:90, direction:'positive', instances:3, confidence:'medium', note:'Defence spending pledges'}]->(s);

// Renewable Energy
MATCH (e:Event {name:'Oil Price Spike'}), (s:Sector {name:'Renewable Energy'})
CREATE (e)-[:CAUSES {strength:0.62, avg_lag_days:30, direction:'positive', instances:3, confidence:'medium', note:'Accelerates energy transition narrative'}]->(s);

// ── RootCause Node Schema ────────────────────────────────────────────────────
// RootCause nodes represent specific real-world triggers (e.g. "OPEC cuts 2M bbl/day
// on Oct 5") as distinct from Event templates (e.g. "Oil Price Spike").
// Created dynamically by the GraphRAG enricher as signals are processed.

CREATE CONSTRAINT root_cause_name IF NOT EXISTS FOR (rc:RootCause) REQUIRE rc.name IS UNIQUE;

// Example seed: a few well-known historical root causes to bootstrap the graph
CREATE (:RootCause {name: 'OPEC+ production cut 2022', category: 'commodity', date: '2022-10-05', source: 'OPEC', created_at: datetime()})
CREATE (:RootCause {name: 'Russia-Ukraine war 2022', category: 'geopolitical', date: '2022-02-24', source: 'Reuters', created_at: datetime()})
CREATE (:RootCause {name: 'US Fed 75bps hike Jun 2022', category: 'monetary', date: '2022-06-15', source: 'Federal Reserve', created_at: datetime()});

// Link seed root causes to existing events
MATCH (rc:RootCause {name: 'OPEC+ production cut 2022'}), (e:Event {name: 'Oil Price Spike'})
CREATE (rc)-[:TRIGGERS {date: '2022-10-05', confidence: 0.92, source: 'OPEC official statement'}]->(e);

MATCH (rc:RootCause {name: 'Russia-Ukraine war 2022'}), (e:Event {name: 'Oil Price Spike'})
CREATE (rc)-[:TRIGGERS {date: '2022-02-24', confidence: 0.95, source: 'Reuters'}]->(e);

MATCH (rc:RootCause {name: 'Russia-Ukraine war 2022'}), (e:Event {name: 'Global Risk Off'})
CREATE (rc)-[:TRIGGERS {date: '2022-02-24', confidence: 0.90, source: 'Reuters'}]->(e);

MATCH (rc:RootCause {name: 'US Fed 75bps hike Jun 2022'}), (e:Event {name: 'DXY Strengthening'})
CREATE (rc)-[:TRIGGERS {date: '2022-06-15', confidence: 0.88, source: 'Federal Reserve'}]->(e);

MATCH (rc:RootCause {name: 'US Fed 75bps hike Jun 2022'}), (e:Event {name: 'FII Selling'})
CREATE (rc)-[:TRIGGERS {date: '2022-06-15', confidence: 0.80, source: 'Federal Reserve'}]->(e);

RETURN "Knowledge graph seeded successfully" AS status;
