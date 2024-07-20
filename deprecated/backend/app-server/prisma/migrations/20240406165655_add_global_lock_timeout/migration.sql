/*
  Warnings:

  - Added the required column `timeout` to the `GlobalLock` table without a default value. This is not possible if the table is not empty.

*/
-- AlterTable
ALTER TABLE "GlobalLock" ADD COLUMN     "timeout" TIMESTAMP(3) NOT NULL;
