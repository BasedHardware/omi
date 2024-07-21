/*
  Warnings:

  - The primary key for the `GlobalLock` table will be changed. If it partially fails, the table could be left without primary key constraint.
  - You are about to drop the column `createdAt` on the `GlobalLock` table. All the data in the column will be lost.
  - You are about to drop the column `id` on the `GlobalLock` table. All the data in the column will be lost.
  - You are about to drop the column `updatedAt` on the `GlobalLock` table. All the data in the column will be lost.
  - The required column `key` was added to the `GlobalLock` table with a prisma-level default value. This is not possible if the table is not empty. Please add this column as optional, then populate it before making it required.
  - Added the required column `value` to the `GlobalLock` table without a default value. This is not possible if the table is not empty.

*/
-- AlterTable
ALTER TABLE "GlobalLock" DROP CONSTRAINT "GlobalLock_pkey",
DROP COLUMN "createdAt",
DROP COLUMN "id",
DROP COLUMN "updatedAt",
ADD COLUMN     "key" TEXT NOT NULL,
ADD COLUMN     "value" TEXT NOT NULL,
ADD CONSTRAINT "GlobalLock_pkey" PRIMARY KEY ("key");
