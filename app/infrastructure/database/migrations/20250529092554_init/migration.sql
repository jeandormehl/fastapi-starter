-- CreateTable
CREATE TABLE "clients" (
    "id" TEXT NOT NULL,
    "client_id" TEXT NOT NULL,
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
CREATE TABLE "_clients_scopes" (
    "A" TEXT NOT NULL,
    "B" TEXT NOT NULL
);

-- CreateIndex
CREATE UNIQUE INDEX "clients_client_id_key" ON "clients"("client_id");

-- CreateIndex
CREATE UNIQUE INDEX "scopes_name_key" ON "scopes"("name");

-- CreateIndex
CREATE UNIQUE INDEX "_clients_scopes_AB_unique" ON "_clients_scopes"("A", "B");

-- CreateIndex
CREATE INDEX "_clients_scopes_B_index" ON "_clients_scopes"("B");

-- AddForeignKey
ALTER TABLE "_clients_scopes" ADD CONSTRAINT "_clients_scopes_A_fkey" FOREIGN KEY ("A") REFERENCES "clients"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "_clients_scopes" ADD CONSTRAINT "_clients_scopes_B_fkey" FOREIGN KEY ("B") REFERENCES "scopes"("id") ON DELETE CASCADE ON UPDATE CASCADE;
