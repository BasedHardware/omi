/*
  Warnings:

  - The primary key for the `SessionToken` table will be changed. If it partially fails, the table could be left without primary key constraint.
  - A unique constraint covering the columns `[key]` on the table `SessionToken` will be added. If there are existing duplicate values, this will fail.
  - The required column `id` was added to the `SessionToken` table with a prisma-level default value. This is not possible if the table is not empty. Please add this column as optional, then populate it before making it required.

*/
-- AlterTable
ALTER TABLE "SessionToken" DROP CONSTRAINT "SessionToken_pkey",
ADD COLUMN     "id" TEXT NOT NULL,
ADD CONSTRAINT "SessionToken_pkey" PRIMARY KEY ("id");

-- CreateIndex
CREATE UNIQUE INDEX "SessionToken_key_key" ON "SessionToken"("key");
