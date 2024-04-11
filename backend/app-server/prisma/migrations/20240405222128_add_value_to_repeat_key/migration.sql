/*
  Warnings:

  - Added the required column `value` to the `RepeatKey` table without a default value. This is not possible if the table is not empty.

*/
-- AlterTable
ALTER TABLE "RepeatKey" ADD COLUMN     "value" TEXT NOT NULL;
