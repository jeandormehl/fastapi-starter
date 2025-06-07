-- CreateTable
CREATE TABLE "request_logs" (
    "id" TEXT NOT NULL,
    "trace_id" TEXT NOT NULL,
    "request_id" TEXT NOT NULL,
    "method" TEXT NOT NULL,
    "url" TEXT NOT NULL,
    "path" TEXT NOT NULL,
    "query_params" TEXT,
    "headers" JSONB,
    "body" JSONB,
    "content_type" TEXT,
    "content_length" INTEGER,
    "client_ip" TEXT,
    "user_agent" TEXT,
    "status_code" INTEGER,
    "response_headers" JSONB,
    "response_body" JSONB,
    "response_size" INTEGER,
    "start_time" TIMESTAMP(3) NOT NULL,
    "end_time" TIMESTAMP(3),
    "duration_ms" DOUBLE PRECISION,
    "authenticated" BOOLEAN NOT NULL DEFAULT false,
    "client_id" TEXT,
    "scopes" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "error_occurred" BOOLEAN NOT NULL DEFAULT false,
    "error_type" TEXT,
    "error_message" TEXT,
    "error_details" JSONB,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "request_logs_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "request_logs_request_id_key" ON "request_logs"("request_id");

-- CreateIndex
CREATE INDEX "request_logs_trace_id_idx" ON "request_logs"("trace_id");

-- CreateIndex
CREATE INDEX "request_logs_request_id_idx" ON "request_logs"("request_id");

-- CreateIndex
CREATE INDEX "request_logs_method_path_idx" ON "request_logs"("method", "path");

-- CreateIndex
CREATE INDEX "request_logs_status_code_idx" ON "request_logs"("status_code");

-- CreateIndex
CREATE INDEX "request_logs_start_time_idx" ON "request_logs"("start_time");

-- CreateIndex
CREATE INDEX "request_logs_client_ip_idx" ON "request_logs"("client_ip");
