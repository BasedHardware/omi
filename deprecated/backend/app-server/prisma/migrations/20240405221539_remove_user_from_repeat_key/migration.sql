/*
  Warnings:

  - You are about to drop the column `userId` on the `RepeatKey` table. All the data in the column will be lost.

*/
-- DropForeignKey
ALTER TABLE "RepeatKey" DROP CONSTRAINT "RepeatKey_userId_fkey";

-- AlterTable
ALTER TABLE "RepeatKey" DROP COLUMN "userId";
