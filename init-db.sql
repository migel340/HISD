-- Initial PostgreSQL setup script
-- This script runs automatically when the postgres service starts

CREATE SCHEMA IF NOT EXISTS public;

-- Example: Create a customers table
CREATE TABLE IF NOT EXISTS public.customers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Example: Create a transactions table
CREATE TABLE IF NOT EXISTS public.transactions (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES public.customers(id),
    amount DECIMAL(10, 2) NOT NULL,
    transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert sample data
INSERT INTO public.customers (name, email) VALUES
    ('John Doe', 'john@example.com'),
    ('Jane Smith', 'jane@example.com'),
    ('Bob Johnson', 'bob@example.com')
ON CONFLICT DO NOTHING;

INSERT INTO public.transactions (customer_id, amount) VALUES
    (1, 100.50),
    (1, 250.00),
    (2, 75.25),
    (3, 1200.00)
ON CONFLICT DO NOTHING;

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_customers_email ON public.customers(email);
CREATE INDEX IF NOT EXISTS idx_transactions_customer_id ON public.transactions(customer_id);

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'basic_user') THEN
        CREATE USER basic_user WITH PASSWORD 'haslo123';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE business_db TO basic_user;
GRANT USAGE ON SCHEMA public TO basic_user;

GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA public TO basic_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO basic_user;