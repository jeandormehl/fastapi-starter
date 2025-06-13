-- CreateTable
CREATE TABLE "clients" (
    "id" TEXT NOT NULL,
    "client_id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "hashed_secret" TEXT NOT NULL,
    "is_active" BOOLEAN NOT NULL DEFAULT true,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "clients_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "scopes" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "description" TEXT,

    CONSTRAINT "scopes_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "request_logs" (
    "id" TEXT NOT NULL,
    "trace_id" TEXT NOT NULL,
    "request_id" TEXT NOT NULL,
    "auth_method" TEXT,
    "authenticated" BOOLEAN NOT NULL DEFAULT false,
    "body" JSONB,
    "client_id" TEXT,
    "client_ip" TEXT,
    "content_length" INTEGER,
    "content_type" TEXT,
    "duration_ms" DECIMAL(65,30),
    "end_time" TIMESTAMP(3),
    "error_category" TEXT,
    "error_occurred" BOOLEAN NOT NULL DEFAULT false,
    "error_type" TEXT,
    "has_bearer_token" BOOLEAN NOT NULL DEFAULT false,
    "headers" JSONB,
    "logged_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "path" TEXT NOT NULL,
    "path_params" JSONB,
    "query_params" JSONB,
    "request_method" TEXT NOT NULL,
    "request_url" TEXT NOT NULL,
    "response_body" JSONB,
    "response_headers" JSONB,
    "response_size" INTEGER,
    "response_type" TEXT,
    "scopes" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "start_time" TIMESTAMP(3) NOT NULL,
    "status_code" INTEGER,
    "success" BOOLEAN NOT NULL DEFAULT false,
    "user_agent" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "request_logs_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "task_logs" (
    "id" TEXT NOT NULL,
    "task_id" TEXT NOT NULL,
    "task_name" TEXT NOT NULL,
    "trace_id" TEXT,
    "request_id" TEXT,
    "worker_id" TEXT,
    "app_version" TEXT,
    "broker_type" TEXT,
    "completed_at" TIMESTAMP(3),
    "cpu_usage_percent" DECIMAL(65,30),
    "duration_ms" DECIMAL(65,30),
    "error_category" TEXT,
    "error_message" TEXT,
    "error_occurred" BOOLEAN NOT NULL DEFAULT false,
    "error_type" TEXT,
    "execution_environment" TEXT,
    "logged_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "max_retries" INTEGER,
    "memory_usage_mb" DECIMAL(65,30),
    "priority" INTEGER,
    "queue" TEXT,
    "retry_count" INTEGER NOT NULL DEFAULT 0,
    "started_at" TIMESTAMP(3),
    "status" TEXT NOT NULL,
    "submitted_at" TIMESTAMP(3) NOT NULL,
    "task_args" JSONB,
    "task_error" JSONB,
    "task_kwargs" JSONB,
    "task_labels" JSONB,
    "task_result" JSONB,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "task_logs_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "_clients_scopes" (
    "A" TEXT NOT NULL,
    "B" TEXT NOT NULL
);

-- CreateIndex
CREATE UNIQUE INDEX "clients_client_id_key" ON "clients"("client_id");

-- CreateIndex
CREATE UNIQUE INDEX "scopes_name_key" ON "scopes"("name");

-- CreateIndex
CREATE UNIQUE INDEX "request_logs_request_id_key" ON "request_logs"("request_id");

-- CreateIndex
CREATE INDEX "request_logs_trace_id_idx" ON "request_logs"("trace_id");

-- CreateIndex
CREATE INDEX "request_logs_request_id_idx" ON "request_logs"("request_id");

-- CreateIndex
CREATE INDEX "request_logs_request_method_path_idx" ON "request_logs"("request_method", "path");

-- CreateIndex
CREATE INDEX "request_logs_status_code_idx" ON "request_logs"("status_code");

-- CreateIndex
CREATE INDEX "request_logs_start_time_idx" ON "request_logs"("start_time");

-- CreateIndex
CREATE INDEX "request_logs_client_ip_idx" ON "request_logs"("client_ip");

-- CreateIndex
CREATE UNIQUE INDEX "task_logs_task_id_key" ON "task_logs"("task_id");

-- CreateIndex
CREATE INDEX "task_logs_task_id_idx" ON "task_logs"("task_id");

-- CreateIndex
CREATE INDEX "task_logs_task_name_idx" ON "task_logs"("task_name");

-- CreateIndex
CREATE INDEX "task_logs_trace_id_idx" ON "task_logs"("trace_id");

-- CreateIndex
CREATE INDEX "task_logs_status_idx" ON "task_logs"("status");

-- CreateIndex
CREATE INDEX "task_logs_submitted_at_idx" ON "task_logs"("submitted_at");

-- CreateIndex
CREATE INDEX "task_logs_started_at_idx" ON "task_logs"("started_at");

-- CreateIndex
CREATE UNIQUE INDEX "_clients_scopes_AB_unique" ON "_clients_scopes"("A", "B");

-- CreateIndex
CREATE INDEX "_clients_scopes_B_index" ON "_clients_scopes"("B");

-- AddForeignKey
ALTER TABLE "_clients_scopes" ADD CONSTRAINT "_clients_scopes_A_fkey" FOREIGN KEY ("A") REFERENCES "clients"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "_clients_scopes" ADD CONSTRAINT "_clients_scopes_B_fkey" FOREIGN KEY ("B") REFERENCES "scopes"("id") ON DELETE CASCADE ON UPDATE CASCADE;
