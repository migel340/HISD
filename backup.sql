--
-- PostgreSQL database dump
--

-- Dumped from database version 12.22 (Debian 12.22-1.pgdg120+1)
-- Dumped by pg_dump version 12.22 (Debian 12.22-1.pgdg120+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'WIN1252';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: complex; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.complex AS (
	i text,
	n text,
	p text
);


ALTER TYPE public.complex OWNER TO postgres;

--
-- Name: calc_vat(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.calc_vat() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  NEW.cena_vat := ROUND(NEW.cena_netto * 0.23, 2);
  NEW.cena_brutto := ROUND(NEW.cena_netto + NEW.cena_vat, 2);
  RETURN NEW;
END;
$$;


ALTER FUNCTION public.calc_vat() OWNER TO postgres;

--
-- Name: dane(integer); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.dane(integer) RETURNS text
    LANGUAGE sql
    AS $_$select nazwisko from Pracownicy where nr_prac = $1$_$;


ALTER FUNCTION public.dane(integer) OWNER TO postgres;

--
-- Name: dane2(integer); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.dane2(integer) RETURNS public.complex
    LANGUAGE sql
    AS $_$select imie, nazwisko, PESEL from Pracownicy where nr_prac = $1$_$;


ALTER FUNCTION public.dane2(integer) OWNER TO postgres;

--
-- Name: dane3(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.dane3() RETURNS SETOF public.complex
    LANGUAGE sql
    AS $$select imie, nazwisko, PESEL from Pracownicy$$;


ALTER FUNCTION public.dane3() OWNER TO postgres;

--
-- Name: extra_money(integer); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.extra_money(integer) RETURNS real
    LANGUAGE plpgsql
    AS $_$
DECLARE zm real;
BEGIN
SELECT 1.25 * pensja INTO zm FROM pracownicy WHERE nr_prac = $1;
RETURN zm;
END;
$_$;


ALTER FUNCTION public.extra_money(integer) OWNER TO postgres;

--
-- Name: podatek_vat(numeric); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.podatek_vat(numeric) RETURNS numeric
    LANGUAGE sql
    AS $_$
SELECT ROUND($1 * 0.23, 2);
$_$;


ALTER FUNCTION public.podatek_vat(numeric) OWNER TO postgres;

--
-- Name: tytuly_ksiazek(integer); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.tytuly_ksiazek(nr_pracownika integer) RETURNS TABLE(tytul text)
    LANGUAGE sql
    AS $$
	SELECT autor_tytul[i][2]
	FROM Wypozyczenia, generate_subscripts(autor_tytul, 1)
	AS i
	WHERE nr_prac = nr_pracownika
$$;


ALTER FUNCTION public.tytuly_ksiazek(nr_pracownika integer) OWNER TO postgres;

--
-- Name: upd(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.upd() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN NEW.last_updated = now();
RETURN NEW;
END;
$$;


ALTER FUNCTION public.upd() OWNER TO postgres;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: osoby; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.osoby (
    imie character varying(15),
    nazwisko character varying(15),
    pesel character varying(11),
    data_ur timestamp without time zone
);


ALTER TABLE public.osoby OWNER TO postgres;

--
-- Name: osob_view; Type: VIEW; Schema: public; Owner: postgres
--

CREATE VIEW public.osob_view AS
 SELECT osoby.imie,
    osoby.nazwisko,
    osoby.pesel
   FROM public.osoby
  WHERE ((osoby.imie)::text = 'Witold'::text);


ALTER TABLE public.osob_view OWNER TO postgres;

--
-- Name: pracownicy; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.pracownicy (
    nr_prac integer,
    nr_zesp integer,
    pensja real
)
INHERITS (public.osoby);


ALTER TABLE public.pracownicy OWNER TO postgres;

--
-- Name: premie; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.premie (
    nr_prac integer,
    premia_kwartalna integer[],
    last_updated timestamp with time zone
);


ALTER TABLE public.premie OWNER TO postgres;

--
-- Name: towary; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.towary (
    id integer NOT NULL,
    nazwa text,
    cena_netto numeric(10,2)
);


ALTER TABLE public.towary OWNER TO postgres;

--
-- Name: towary2; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.towary2 (
    id integer NOT NULL,
    nazwa text,
    cena_netto numeric(10,2),
    cena_vat numeric(10,2),
    cena_brutto numeric(10,2)
);


ALTER TABLE public.towary2 OWNER TO postgres;

--
-- Name: wypozyczenia; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.wypozyczenia (
    nr_prac integer,
    autor_tytul text[]
);


ALTER TABLE public.wypozyczenia OWNER TO postgres;

--
-- Data for Name: osoby; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.osoby (imie, nazwisko, pesel, data_ur) FROM stdin;
Jan	Nowak	11111111111	1988-01-01 00:00:00
Adam	Kowalski	22222222222	1989-10-01 00:00:00
Anna	Krol	33333333333	1990-10-15 00:00:00
Abc	Abc	11111111111	\N
\.


--
-- Data for Name: pracownicy; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.pracownicy (imie, nazwisko, pesel, data_ur, nr_prac, nr_zesp, pensja) FROM stdin;
Tomasz	Wicek	44444444444	1978-12-12 00:00:00	1	10	2500
Witold	Wrembel	88888888888	1977-02-02 00:00:00	2	10	1950
Kamila	Bialek	99999999999	1983-12-12 00:00:00	3	30	2000
\.


--
-- Data for Name: premie; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.premie (nr_prac, premia_kwartalna, last_updated) FROM stdin;
1	{100,150,200,250}	\N
2	{300,150,100,150}	2025-05-26 10:56:58.880483-05
\.


--
-- Data for Name: towary; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.towary (id, nazwa, cena_netto) FROM stdin;
1	kabel	50.00
2	laptop	940.00
3	monitor	600.00
\.


--
-- Data for Name: towary2; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.towary2 (id, nazwa, cena_netto, cena_vat, cena_brutto) FROM stdin;
1	abc	100.00	23.00	123.00
\.


--
-- Data for Name: wypozyczenia; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.wypozyczenia (nr_prac, autor_tytul) FROM stdin;
1	{{Tolkien,Hobbit,Iskry,1980},{Dickens,"Klub Pickwicka",MG,1989},{Stone,"Pasja zycia","ZYSK I S-KA",1999}}
2	{{Pascal,Przewodnik,"lonely planet",2010},{Archer,"Co do grosza","Rebis Sp. z.o.o.",1999}}
\.


--
-- Name: towary2 towary2_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.towary2
    ADD CONSTRAINT towary2_pkey PRIMARY KEY (id);


--
-- Name: towary towary_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.towary
    ADD CONSTRAINT towary_pkey PRIMARY KEY (id);


--
-- Name: pracownicy pozytywne_id; Type: RULE; Schema: public; Owner: postgres
--

CREATE RULE pozytywne_id AS
    ON INSERT TO public.pracownicy
   WHERE (new.nr_prac <= 0) DO INSTEAD NOTHING;


--
-- Name: osob_view reg2; Type: RULE; Schema: public; Owner: postgres
--

CREATE RULE reg2 AS
    ON INSERT TO public.osob_view DO INSTEAD  INSERT INTO public.osoby (imie, nazwisko, pesel)
  VALUES (new.imie, new.nazwisko, new.pesel);


--
-- Name: premie last_upd; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER last_upd BEFORE INSERT OR UPDATE ON public.premie FOR EACH ROW EXECUTE FUNCTION public.upd();


--
-- Name: towary2 vat_calc; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER vat_calc BEFORE INSERT OR UPDATE ON public.towary2 FOR EACH ROW EXECUTE FUNCTION public.calc_vat();


--
-- PostgreSQL database dump complete
--

