-- CreateTable
CREATE TABLE "Update" (
    "userId" TEXT NOT NULL,
    "seq" INTEGER NOT NULL,
    "repeatKey" TEXT,
    "data" JSONB NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- CreateIndex
CREATE UNIQUE INDEX "Update_userId_seq_key" ON "Update"("userId", "seq");

-- AddForeignKey
ALTER TABLE "Update" ADD CONSTRAINT "Update_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
